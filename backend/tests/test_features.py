"""Tests for feature engineering — including the critical anti-leakage check."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.preprocessing.features import (
    MODULE_B_INPUT_FEATURES,
    FORBIDDEN_MODULE_B_FEATURES,
    compute_lot_stats,
    engineer_features,
    get_module_b_feature_columns,
    assert_no_leakage,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_feature_df() -> pd.DataFrame:
    """Create a minimal multi-component, multi-lot dataframe for testing."""
    rows = []
    for i in range(10):
        for param, spec_min, spec_max in [
            ("iddq", 0.1, 5.0),
            ("leakage_current", 0.0, 50.0),
            ("propagation_delay", 1.0, 15.0),
        ]:
            rows.append({
                "component_id": f"C{i:03d}",
                "lot_id": "LOT-001" if i < 5 else "LOT-002",
                "parameter": param,
                "value_0h": 1.0 + i * 0.1,
                "value_24h": 1.1 + i * 0.1,
                "value_96h": 1.2 + i * 0.1,
                "value_168h": 1.3 + i * 0.1,
                "spec_min": spec_min,
                "spec_max": spec_max,
                "temperature_profile": "125C",
                "label": "healthy",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Anti-leakage test (CRITICAL)
# ---------------------------------------------------------------------------

class TestAntiLeakage:
    """CRITICAL: Module B must never use 168h-derived features as inputs."""

    def test_module_b_features_contain_no_forbidden(self):
        """Assert no forbidden feature names appear in MODULE_B_INPUT_FEATURES."""
        for forbidden in FORBIDDEN_MODULE_B_FEATURES:
            assert forbidden not in MODULE_B_INPUT_FEATURES, (
                f"LEAKAGE DETECTED: '{forbidden}' is in MODULE_B_INPUT_FEATURES!"
            )

    def test_get_module_b_feature_columns_no_leakage(self):
        """get_module_b_feature_columns() must not include any forbidden feature."""
        cols = get_module_b_feature_columns(use_96h=True)
        for forbidden in FORBIDDEN_MODULE_B_FEATURES:
            assert forbidden not in cols, (
                f"LEAKAGE DETECTED: '{forbidden}' returned by get_module_b_feature_columns!"
            )

    def test_get_module_b_feature_columns_no_96h(self):
        """When use_96h=False, all 96h features should be absent."""
        cols = get_module_b_feature_columns(use_96h=False)
        for col in cols:
            assert "96" not in col, f"96h feature '{col}' present when use_96h=False"
        for forbidden in FORBIDDEN_MODULE_B_FEATURES:
            assert forbidden not in cols

    def test_assert_no_leakage_raises_on_forbidden(self):
        """assert_no_leakage() must raise AssertionError if forbidden col present."""
        bad_features = list(MODULE_B_INPUT_FEATURES) + ["value_168h"]
        with pytest.raises(AssertionError, match="leakage"):
            assert_no_leakage(bad_features)

    def test_assert_no_leakage_passes_on_valid(self):
        """assert_no_leakage() must NOT raise on the canonical feature set."""
        assert_no_leakage(MODULE_B_INPUT_FEATURES)  # must not raise

    def test_engineered_features_delta_168_not_in_b_features(self):
        """After engineer_features(), delta_168 must not be in Module B feature list."""
        df = make_feature_df()
        lot_stats = compute_lot_stats(df)
        featured = engineer_features(df, lot_stats)
        # delta_168 IS computed (for eval), but must not be a Module B input
        assert "delta_168" in featured.columns, "delta_168 should exist for eval purposes"
        b_cols = get_module_b_feature_columns(use_96h=True)
        assert "delta_168" not in b_cols
        assert "slope_96_168" not in b_cols


# ---------------------------------------------------------------------------
# Lot stats tests
# ---------------------------------------------------------------------------

class TestComputeLotStats:
    def test_returns_median_and_mad(self):
        df = make_feature_df()
        stats = compute_lot_stats(df)
        # At least one key should be present
        assert len(stats) > 0
        # Keys should be (lot_id, param, checkpoint) tuples
        for key, (median, mad) in stats.items():
            assert len(key) == 3
            assert isinstance(median, float)
            assert isinstance(mad, float)
            assert mad >= 0

    def test_global_fallback_present(self):
        df = make_feature_df()
        stats = compute_lot_stats(df)
        # Should have global fallback keys
        global_keys = [k for k in stats if k[0] == "__global__"]
        assert len(global_keys) > 0

    def test_train_only_ids_respected(self):
        df = make_feature_df()
        train_ids = {f"C{i:03d}" for i in range(5)}
        stats = compute_lot_stats(df, train_component_ids=train_ids)
        # Stats should exist; values should reflect only train components
        assert len(stats) > 0


# ---------------------------------------------------------------------------
# Engineer features tests
# ---------------------------------------------------------------------------

class TestEngineerFeatures:
    def test_all_expected_columns_present(self):
        df = make_feature_df()
        featured = engineer_features(df)
        expected_cols = [
            "delta_24", "delta_96", "delta_168",
            "slope_0_24", "slope_24_96", "acceleration",
            "margin_to_spec_max", "margin_to_spec_min",
            "robust_z_0h", "robust_z_24h", "robust_z_96h",
            "lot_median_0h", "lot_mad_0h",
        ]
        for col in expected_cols:
            assert col in featured.columns, f"Missing column: {col}"

    def test_delta_24_correct(self):
        df = make_feature_df()
        featured = engineer_features(df)
        pd.testing.assert_series_equal(
            featured["delta_24"],
            featured["value_24h"] - featured["value_0h"],
            check_names=False,
        )

    def test_slope_0_24_correct(self):
        df = make_feature_df()
        featured = engineer_features(df)
        expected = (featured["value_24h"] - featured["value_0h"]) / 24.0
        pd.testing.assert_series_equal(featured["slope_0_24"], expected, check_names=False)

    def test_margin_to_spec_max_non_negative_for_valid(self):
        """For in-spec components, margin_to_spec_max should be >= 0."""
        df = make_feature_df()
        featured = engineer_features(df)
        assert (featured["margin_to_spec_max"] >= 0).all()

    def test_robust_z_zero_for_uniform_lot(self):
        """When all components in a lot have the same value, z-score should be ~0."""
        rows = []
        for i in range(5):
            rows.append({
                "component_id": f"C{i}",
                "lot_id": "LOT-001",
                "parameter": "iddq",
                "value_0h": 2.0,  # all same
                "value_24h": 2.1,
                "value_96h": 2.2,
                "value_168h": 2.3,
                "spec_min": 0.1,
                "spec_max": 5.0,
                "label": "healthy",
                "temperature_profile": "125C",
            })
        df = pd.DataFrame(rows)
        featured = engineer_features(df)
        # When MAD=0, z-score defaults to 0
        assert (featured["robust_z_0h"].abs() < 1e-6).all()

    def test_missing_value_96h_handled(self):
        """Missing value_96h should not crash feature engineering."""
        df = make_feature_df()
        df.loc[0, "value_96h"] = np.nan
        # Should not raise
        featured = engineer_features(df)
        assert len(featured) == len(df)
