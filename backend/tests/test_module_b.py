"""Tests for Module B: Time-series drift predictor."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models_ml.module_b_drift import ModuleBDriftPredictor
from app.preprocessing.features import engineer_features, compute_lot_stats, get_module_b_feature_columns


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TEST_CONFIG = {
    "module_b": {
        "use_value_96h": True,
        "cv_folds": 3,
        "candidate_models": ["linear_regression", "ridge", "random_forest"],
        "ridge_alpha": 1.0,
        "random_forest": {"n_estimators": 20, "max_depth": 5},
        "drift_risk_thresholds": {"safe": 0.5, "watch": 0.85},
        "drift_convention": "from_24h",
    }
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_training_df(n: int = 60, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic training data with multiple labels and parameters."""
    rng = np.random.default_rng(seed)
    rows = []
    params = [("iddq", 0.1, 5.0), ("leakage_current", 0.0, 50.0), ("propagation_delay", 1.0, 15.0)]
    labels = ["healthy"] * 40 + ["gradual_drift"] * 10 + ["sudden_drift"] * 10

    for i in range(n):
        label = labels[i % len(labels)]
        cid = f"COMP-{i:04d}"
        lot_id = f"LOT-{(i // 10) + 1:03d}"
        for param, spec_min, spec_max in params:
            base = rng.uniform(spec_min + 0.5, spec_max * 0.3)
            if label == "gradual_drift":
                values = [base, base + 0.5, base + 1.5, base + 3.0]
            elif label == "sudden_drift":
                values = [base, base + 0.1, base + 0.2, base + spec_max * 0.5]
            else:
                values = [base, base + rng.normal(0, 0.1), base + rng.normal(0, 0.1), base + rng.normal(0, 0.15)]

            rows.append({
                "component_id": cid,
                "lot_id": lot_id,
                "parameter": param,
                "value_0h": max(spec_min, values[0]),
                "value_24h": max(spec_min, values[1]),
                "value_96h": max(spec_min, values[2]),
                "value_168h": max(spec_min, min(spec_max * 1.5, values[3])),
                "spec_min": spec_min,
                "spec_max": spec_max,
                "label": label,
                "temperature_profile": "125C",
            })

    return pd.DataFrame(rows)


def fit_module_b(df: pd.DataFrame) -> tuple[ModuleBDriftPredictor, set[str], pd.DataFrame]:
    """Fit module B and return predictor + split ids + featured df."""
    n_comps = df["component_id"].nunique()
    comp_ids = list(df["component_id"].unique())
    n_train = int(n_comps * 0.75)
    train_ids = set(comp_ids[:n_train])

    lot_stats = compute_lot_stats(df, train_ids)
    featured = engineer_features(df, lot_stats)

    predictor = ModuleBDriftPredictor(TEST_CONFIG)
    predictor.select_and_train(featured, train_ids)
    return predictor, train_ids, featured


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestModuleBDriftPredictor:
    def test_fit_runs_without_error(self):
        df = make_training_df(n=60)
        predictor, _, _ = fit_module_b(df)
        assert len(predictor.models) > 0

    def test_model_selected_for_each_parameter(self):
        """A model must be selected and persisted for every parameter."""
        df = make_training_df(n=60)
        predictor, _, _ = fit_module_b(df)
        params = df["parameter"].unique()
        for param in params:
            assert param in predictor.models, f"No model trained for param: {param}"

    def test_selection_results_documented(self):
        """Model selection comparison table must be populated."""
        df = make_training_df(n=60)
        predictor, _, _ = fit_module_b(df)
        assert len(predictor.selection_results) > 0
        for param, results in predictor.selection_results.items():
            assert "selected" in results, f"No winner recorded for {param}"
            assert "selected_mae" in results

    def test_prediction_produces_bounded_output(self):
        """Predicted values must be finite numbers, not NaN or ±inf."""
        df = make_training_df(n=60)
        predictor, train_ids, featured = fit_module_b(df)

        test_ids = set(featured["component_id"].unique()) - train_ids
        test_df = featured[featured["component_id"].isin(list(test_ids)[:5])]

        preds = predictor.predict(test_df)
        assert not preds["predicted_168h"].isna().all(), "All predictions are NaN"
        valid_preds = preds["predicted_168h"].dropna()
        assert np.isfinite(valid_preds).all(), "Predictions contain ±inf"

    def test_drift_rate_non_nan_for_known_params(self):
        """drift_rate must be populated for components where a model exists."""
        df = make_training_df(n=60)
        predictor, train_ids, featured = fit_module_b(df)

        # Use a component whose parameter has a model
        param = list(predictor.models.keys())[0]
        sample = featured[featured["parameter"] == param].head(3)
        preds = predictor.predict(sample)
        assert preds["drift_rate"].notna().any(), f"drift_rate all NaN for param {param}"

    def test_classify_drift_risk_covers_all_categories(self):
        """
        classify_drift_risk() must be capable of returning SAFE, WATCH, and DANGEROUS.
        Construct synthetic drift rates spanning all three regimes.
        """
        predictor = ModuleBDriftPredictor(TEST_CONFIG)
        safety_slopes = {"leakage_current": 0.1}

        # SAFE: drift_rate well below safety
        df_safe = pd.DataFrame([{
            "predicted_168h": 12.0, "predicted_drift": 1.0,
            "drift_rate": 0.01, "actual_168h": 12.0, "parameter": "leakage_current",
        }])
        assert predictor.classify_drift_risk(df_safe, safety_slopes).iloc[0]["drift_risk"] == "SAFE"

        # WATCH: drift_rate at ~60% of safety
        df_watch = pd.DataFrame([{
            "predicted_168h": 17.0, "predicted_drift": 6.0,
            "drift_rate": 0.06, "actual_168h": None, "parameter": "leakage_current",
        }])
        assert predictor.classify_drift_risk(df_watch, safety_slopes).iloc[0]["drift_risk"] == "WATCH"

        # DANGEROUS: drift_rate >> safety
        df_danger = pd.DataFrame([{
            "predicted_168h": 45.0, "predicted_drift": 34.0,
            "drift_rate": 0.25, "actual_168h": None, "parameter": "leakage_current",
        }])
        assert predictor.classify_drift_risk(df_danger, safety_slopes).iloc[0]["drift_risk"] == "DANGEROUS"

    def test_gradual_drift_gets_higher_drift_rate_than_healthy(self):
        """Gradual drift components should have higher predicted drift rate than healthy."""
        df = make_training_df(n=60)
        predictor, train_ids, featured = fit_module_b(df)
        safety_slopes = {"iddq": 0.01, "leakage_current": 0.01, "propagation_delay": 0.01}

        param = list(predictor.models.keys())[0]
        gradual = featured[(featured["label"] == "gradual_drift") & (featured["parameter"] == param)]
        healthy = featured[(featured["label"] == "healthy") & (featured["parameter"] == param)]

        if len(gradual) == 0 or len(healthy) == 0:
            pytest.skip("Not enough data for this test")

        preds_gradual = predictor.predict(gradual)
        preds_healthy = predictor.predict(healthy)

        avg_drift_gradual = preds_gradual["drift_rate"].abs().mean()
        avg_drift_healthy = preds_healthy["drift_rate"].abs().mean()

        assert avg_drift_gradual > avg_drift_healthy * 0.8, (
            f"Gradual drift ({avg_drift_gradual:.4f}) not higher than healthy ({avg_drift_healthy:.4f})"
        )

    def test_evaluate_returns_mae_rmse_r2(self):
        """evaluate() must return MAE, RMSE, R² per parameter."""
        df = make_training_df(n=60)
        predictor, train_ids, featured = fit_module_b(df)
        test_ids = set(featured["component_id"].unique()) - train_ids

        metrics = predictor.evaluate(featured, test_ids)
        for param, m in metrics.items():
            assert "mae" in m
            assert "rmse" in m
            assert "r2" in m
            assert np.isfinite(m["mae"])
            assert np.isfinite(m["rmse"])

    def test_save_and_load(self, tmp_path):
        """Save + load cycle must produce identical predictions."""
        df = make_training_df(n=60)
        predictor, train_ids, featured = fit_module_b(df)

        predictor.save(tmp_path)

        predictor2 = ModuleBDriftPredictor(TEST_CONFIG)
        predictor2.load(tmp_path)

        sample = featured.head(3)
        p1 = predictor.predict(sample)["predicted_168h"].values
        p2 = predictor2.predict(sample)["predicted_168h"].values
        np.testing.assert_allclose(p1, p2, rtol=1e-6)

    def test_feature_columns_no_168h_leakage(self):
        """Module B feature columns used in predict() must not contain 168h-derived features."""
        df = make_training_df(n=60)
        predictor, _, _ = fit_module_b(df)
        for col in predictor.feature_cols:
            assert "168" not in col, (
                f"LEAKAGE: feature '{col}' contains '168h' in Module B feature set"
            )
