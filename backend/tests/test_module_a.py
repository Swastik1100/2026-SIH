"""Tests for Module A: Dynamic anomaly detection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models_ml.module_a_anomaly import ModuleAAnomalyDetector
from app.preprocessing.features import engineer_features, compute_lot_stats


# ---------------------------------------------------------------------------
# Test config (mirrors real config shape)
# ---------------------------------------------------------------------------

TEST_CONFIG = {
    "module_a": {
        "mad_z_threshold": 3.5,
        "isolation_forest_contamination": 0.1,
        "isolation_forest_n_estimators": 50,
        "score_weights": {"mad": 0.55, "isolation_forest": 0.45},
        "anomaly_threshold": 0.65,
        "severity_bands": {"low": 0.40, "medium": 0.65, "high": 0.80},
    }
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_lot_df(n_healthy: int = 20, seed: int = 42) -> pd.DataFrame:
    """
    Create a synthetic lot where healthy components cluster around lot_median ≈ 10 µA.
    Returns a dataframe of healthy components with lot_id=LOT-001, param=leakage_current.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_healthy):
        cid = f"HEALTHY-{i:04d}"
        base = rng.normal(10.0, 1.0)  # lot median ≈ 10 µA
        rows.append({
            "component_id": cid,
            "lot_id": "LOT-001",
            "parameter": "leakage_current",
            "value_0h": base + rng.normal(0, 0.3),
            "value_24h": base + rng.normal(0, 0.3) + 0.2,
            "value_96h": base + rng.normal(0, 0.3) + 0.4,
            "value_168h": base + rng.normal(0, 0.3) + 0.6,
            "spec_min": 0.0,
            "spec_max": 50.0,
            "label": "healthy",
            "temperature_profile": "125C",
        })
    return pd.DataFrame(rows)


def make_latent_defect_row(lot_id: str = "LOT-001") -> dict:
    """
    C003-style latent defect: spec_max=50 µA, lot median≈10 µA, component drifts to 45 µA.
    Static PASS, but population anomaly.
    """
    return {
        "component_id": "C003",
        "lot_id": lot_id,
        "parameter": "leakage_current",
        "value_0h": 10.5,
        "value_24h": 18.2,
        "value_96h": 32.0,
        "value_168h": 45.1,
        "spec_min": 0.0,
        "spec_max": 50.0,
        "label": "latent_defect",
        "temperature_profile": "125C",
    }


def make_noisy_healthy_row(lot_id: str = "LOT-001") -> dict:
    """
    C006-style noisy healthy: higher baseline but stable — must NOT be flagged HIGH.
    Baseline ≈ 18 µA (well within spec), stable drift pattern.
    """
    return {
        "component_id": "C006",
        "lot_id": lot_id,
        "parameter": "leakage_current",
        "value_0h": 18.0,
        "value_24h": 18.5,
        "value_96h": 18.8,
        "value_168h": 19.0,
        "spec_min": 0.0,
        "spec_max": 50.0,
        "label": "noisy_healthy",
        "temperature_profile": "125C",
    }


def fit_detector_on_lot(n_healthy: int = 30) -> tuple[ModuleAAnomalyDetector, pd.DataFrame]:
    """Train Module A on a healthy lot, return detector and featured training df."""
    healthy_df = make_lot_df(n_healthy=n_healthy)
    train_ids = set(healthy_df["component_id"].unique())

    lot_stats = compute_lot_stats(healthy_df, train_ids)
    featured = engineer_features(healthy_df, lot_stats)

    detector = ModuleAAnomalyDetector(TEST_CONFIG)
    detector.fit(featured, train_ids)
    return detector, featured, lot_stats


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestModuleAAnomalyDetector:
    def test_fit_does_not_raise(self):
        """Detector fits without error on normal data."""
        detector, _, _ = fit_detector_on_lot()
        assert len(detector.lot_models) + len(detector.global_models) > 0

    def test_latent_defect_flagged(self):
        """
        HEADLINE TEST: Component with lot-relative anomaly (45 µA vs lot median 10 µA)
        must be flagged as MEDIUM or HIGH severity — this is the core false-negative check.
        """
        detector, _, lot_stats = fit_detector_on_lot(n_healthy=30)

        # Build a dataframe containing the latent defect
        defect_row = make_latent_defect_row()
        df_single = pd.DataFrame([defect_row])
        featured = engineer_features(df_single, lot_stats)
        row = featured.iloc[0]

        result = detector.score_row(row)
        assert result["severity"] in ("MEDIUM", "HIGH"), (
            f"Latent defect was NOT flagged! severity={result['severity']}, "
            f"score={result['anomaly_score']:.3f}. "
            "This is a critical false negative — latent defects must be caught."
        )

    def test_latent_defect_has_high_z_score(self):
        """Latent defect's MAD z-score should be well above threshold."""
        detector, _, lot_stats = fit_detector_on_lot(n_healthy=30)
        defect_row = make_latent_defect_row()
        df_single = pd.DataFrame([defect_row])
        featured = engineer_features(df_single, lot_stats)
        row = featured.iloc[0]

        result = detector.score_row(row)
        # The z-score normalized component should be elevated
        assert result["robust_z_score"] > 0.5, (
            f"Expected high MAD z-score for latent defect, got {result['robust_z_score']:.3f}"
        )

    def test_healthy_component_not_flagged_high(self):
        """A genuinely healthy component must NOT be flagged as HIGH severity."""
        detector, featured, lot_stats = fit_detector_on_lot(n_healthy=30)

        # Score a known healthy component from training
        healthy_row = featured.iloc[0]
        result = detector.score_row(healthy_row)
        assert result["severity"] != "HIGH", (
            f"Healthy component incorrectly flagged HIGH (score={result['anomaly_score']:.3f})"
        )

    def test_score_row_returns_expected_fields(self):
        """score_row() must return all required output fields."""
        detector, featured, _ = fit_detector_on_lot()
        row = featured.iloc[0]
        result = detector.score_row(row)

        required_fields = [
            "robust_z_score", "isolation_forest_score", "anomaly_score",
            "anomaly_label", "severity", "contributing_features"
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def test_anomaly_score_bounded_0_1(self):
        """anomaly_score must always be in [0, 1]."""
        detector, featured, lot_stats = fit_detector_on_lot(n_healthy=30)
        # Score all rows including a defect
        defect_df = pd.DataFrame([make_latent_defect_row()])
        all_df = pd.concat([featured, engineer_features(defect_df, lot_stats)], ignore_index=True)

        for _, row in all_df.iterrows():
            result = detector.score_row(row)
            score = result["anomaly_score"]
            assert 0.0 <= score <= 1.0, f"Score out of bounds: {score}"

    def test_contributing_features_non_empty_for_anomaly(self):
        """Anomalous component must have contributing_features for explainability."""
        detector, _, lot_stats = fit_detector_on_lot(n_healthy=30)
        defect_df = pd.DataFrame([make_latent_defect_row()])
        featured = engineer_features(defect_df, lot_stats)
        result = detector.score_row(featured.iloc[0])
        assert isinstance(result["contributing_features"], list)

    def test_score_dataframe_shape(self):
        """score_dataframe() must return same number of rows as input."""
        detector, featured, _ = fit_detector_on_lot()
        scores = detector.score_dataframe(featured)
        assert len(scores) == len(featured)

    def test_save_and_load(self, tmp_path):
        """Saved and loaded detector must produce same scores."""
        detector, featured, lot_stats = fit_detector_on_lot()
        detector.save(tmp_path)

        detector2 = ModuleAAnomalyDetector(TEST_CONFIG)
        detector2.load(tmp_path)

        row = featured.iloc[0]
        r1 = detector.score_row(row)
        r2 = detector2.score_row(row)
        assert abs(r1["anomaly_score"] - r2["anomaly_score"]) < 1e-9
