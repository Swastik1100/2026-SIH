"""Tests for safety slope computation."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models_ml.safety_slope import compute_safety_slopes


@pytest.fixture
def base_config():
    return {
        "safety_slope": {
            "healthy_percentile": 95,
            "horizon_hours": 168,
            "use_spec_headroom": True,
            "spec_headroom_fraction": 0.8,
        },
        "parameters": {
            "iddq": {"spec_min": 0.1, "spec_max": 5.0},
            "leakage_current": {"spec_min": 0.0, "spec_max": 50.0},
            "propagation_delay": {"spec_min": 1.0, "spec_max": 15.0},
        },
    }


@pytest.fixture
def labeled_df():
    """Minimal DataFrame with labels for safety slope computation."""
    rng = np.random.default_rng(42)
    rows = []
    params = [
        ("iddq", 1.5, 0.3, 5.0),
        ("leakage_current", 10.0, 3.0, 50.0),
        ("propagation_delay", 5.0, 1.0, 15.0),
    ]
    for comp_idx in range(50):
        cid = f"C{comp_idx:04d}"
        lot = f"LOT-{comp_idx // 10 + 1:03d}"
        for param, mean, std, spec_max in params:
            v0 = rng.normal(mean, std * 0.5)
            drift = rng.uniform(0.0, 0.02) * mean
            v24 = v0 + drift + rng.normal(0, std * 0.1)
            v96 = v24 + drift + rng.normal(0, std * 0.1)
            v168 = v96 + drift + rng.normal(0, std * 0.1)
            rows.append({
                "component_id": cid,
                "lot_id": lot,
                "parameter": param,
                "value_0h": v0,
                "value_24h": v24,
                "value_96h": v96,
                "value_168h": v168,
                "spec_min": 0.0,
                "spec_max": spec_max,
                "label": "healthy",
            })
    # Add a few defects
    for comp_idx in range(5):
        cid = f"DEF{comp_idx:04d}"
        rows.append({
            "component_id": cid, "lot_id": "LOT-001",
            "parameter": "leakage_current",
            "value_0h": 10.0, "value_24h": 25.0, "value_96h": 40.0, "value_168h": 48.0,
            "spec_min": 0.0, "spec_max": 50.0, "label": "latent_defect",
        })
    return pd.DataFrame(rows)


class TestSafetySlopes:
    def test_returns_slope_for_each_parameter(self, labeled_df, base_config):
        slopes = compute_safety_slopes(labeled_df, base_config)
        assert "iddq" in slopes
        assert "leakage_current" in slopes
        assert "propagation_delay" in slopes

    def test_all_slopes_are_positive(self, labeled_df, base_config):
        slopes = compute_safety_slopes(labeled_df, base_config)
        for param, slope in slopes.items():
            assert slope > 0, f"Safety slope for {param} must be positive, got {slope}"

    def test_slope_is_below_spec_headroom_rate(self, labeled_df, base_config):
        """Slope should be physically reasonable — not larger than full-range per hour."""
        slopes = compute_safety_slopes(labeled_df, base_config)
        spec_maxes = {"iddq": 5.0, "leakage_current": 50.0, "propagation_delay": 15.0}
        for param, slope in slopes.items():
            max_possible = spec_maxes[param] / 24.0  # full range in 24h
            assert slope < max_possible, f"{param} slope {slope:.4f} exceeds physical maximum {max_possible:.4f}"

    def test_minimum_slope_guard(self, labeled_df, base_config):
        """Slopes must be at least 1e-8 to prevent division by zero."""
        slopes = compute_safety_slopes(labeled_df, base_config)
        for param, slope in slopes.items():
            assert slope >= 1e-8

    def test_fallback_when_no_healthy_components(self, base_config):
        """When there are no healthy components, should return a non-zero fallback."""
        df = pd.DataFrame([{
            "component_id": "C001", "lot_id": "LOT-001",
            "parameter": "iddq",
            "value_0h": 1.0, "value_24h": 2.0, "value_96h": 3.0, "value_168h": 4.0,
            "spec_min": 0.0, "spec_max": 5.0, "label": "latent_defect",
        }])
        slopes = compute_safety_slopes(df, base_config)
        assert "iddq" in slopes
        assert slopes["iddq"] > 0

    def test_reproducibility(self, labeled_df, base_config):
        """Safety slopes should be deterministic."""
        slopes1 = compute_safety_slopes(labeled_df, base_config)
        slopes2 = compute_safety_slopes(labeled_df, base_config)
        assert slopes1 == slopes2
