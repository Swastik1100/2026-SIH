"""Module B: Time-series drift predictor with model selection.

Candidates: Linear Regression, Ridge, Random Forest, XGBoost Regressor, Gradient Boosting.
Best model is selected per-parameter by cross-validated MAE.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_val_score

try:
    from xgboost import XGBRegressor
    _XGB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _XGB_AVAILABLE = False

from app.preprocessing.features import get_module_b_feature_columns

logger = logging.getLogger(__name__)


def _get_model(name: str, config: dict[str, Any]):
    b_cfg = config["module_b"]
    if name == "linear_regression":
        return LinearRegression()
    if name == "ridge":
        return Ridge(alpha=b_cfg.get("ridge_alpha", 1.0))
    if name == "random_forest":
        rf_cfg = b_cfg.get("random_forest", {})
        return RandomForestRegressor(
            n_estimators=rf_cfg.get("n_estimators", 200),
            max_depth=rf_cfg.get("max_depth", 10),
            random_state=42,
            n_jobs=-1,
        )
    if name == "xgboost_regressor":
        if not _XGB_AVAILABLE:
            raise ValueError("xgboost not installed — run: pip install xgboost>=2.0.0")
        xgb_cfg = b_cfg.get("xgboost_regressor", {})
        return XGBRegressor(
            n_estimators=xgb_cfg.get("n_estimators", 300),
            max_depth=xgb_cfg.get("max_depth", 6),
            learning_rate=xgb_cfg.get("learning_rate", 0.05),
            subsample=xgb_cfg.get("subsample", 0.8),
            colsample_bytree=xgb_cfg.get("colsample_bytree", 0.8),
            random_state=42,
            n_jobs=-1,
        )
    if name == "gradient_boosting":
        gb_cfg = b_cfg.get("gradient_boosting", {})
        return GradientBoostingRegressor(
            n_estimators=gb_cfg.get("n_estimators", 200),
            max_depth=gb_cfg.get("max_depth", 5),
            learning_rate=gb_cfg.get("learning_rate", 0.05),
            random_state=42,
        )
    raise ValueError(f"Unknown model: {name}")


class ModuleBDriftPredictor:
    """Per-parameter drift predictor with documented model selection."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.models: dict[str, Any] = {}
        self.feature_cols: list[str] = []
        self.selection_results: dict[str, Any] = {}
        self.use_96h = config["module_b"].get("use_value_96h", True)

    def _prepare_data(self, df: pd.DataFrame, train_ids: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
        self.feature_cols = get_module_b_feature_columns(self.use_96h)
        train = df[df["component_id"].isin(train_ids)].dropna(subset=["value_168h"])
        test = df[~df["component_id"].isin(train_ids)].dropna(subset=["value_168h"])
        return train, test

    def select_and_train(self, df: pd.DataFrame, train_ids: set[str]) -> dict[str, Any]:
        train_df, _ = self._prepare_data(df, train_ids)
        candidates = self.config["module_b"]["candidate_models"]
        # Skip xgboost_regressor if not available
        if not _XGB_AVAILABLE and "xgboost_regressor" in candidates:
            candidates = [c for c in candidates if c != "xgboost_regressor"]
            logger.warning("xgboost not installed — skipping xgboost_regressor candidate.")
        cv_folds = self.config["module_b"].get("cv_folds", 5)
        all_results: dict[str, Any] = {}

        for param in train_df["parameter"].unique():
            param_df = train_df[train_df["parameter"] == param]
            X = param_df[self.feature_cols].fillna(0).values
            y = param_df["value_168h"].values

            if len(X) < cv_folds + 1:
                logger.warning("Insufficient data for param %s", param)
                continue

            param_results = {}
            best_model_name = None
            best_mae = float("inf")

            for model_name in candidates:
                try:
                    model = _get_model(model_name, self.config)
                    scores = cross_val_score(
                        model, X, y, cv=cv_folds, scoring="neg_mean_absolute_error"
                    )
                    mae = -scores.mean()
                    rmse_scores = cross_val_score(
                        model, X, y, cv=cv_folds, scoring="neg_root_mean_squared_error"
                    )
                    rmse = -rmse_scores.mean()
                    param_results[model_name] = {"mae": round(mae, 6), "rmse": round(rmse, 6)}
                    if mae < best_mae:
                        best_mae = mae
                        best_model_name = model_name
                except Exception as e:
                    logger.warning("Model %s failed for %s: %s", model_name, param, e)

            if best_model_name:
                final_model = _get_model(best_model_name, self.config)
                final_model.fit(X, y)
                self.models[param] = final_model
                param_results["selected"] = best_model_name
                param_results["selected_mae"] = round(best_mae, 6)
                logger.info(
                    "Param %s: selected %s (MAE=%.4f)", param, best_model_name, best_mae
                )

            all_results[param] = param_results

        self.selection_results = all_results
        return all_results

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        predictions = []
        for _, row in df.iterrows():
            param = row["parameter"]
            if param not in self.models:
                predictions.append({"predicted_168h": np.nan, "predicted_drift": np.nan})
                continue
            X = row[self.feature_cols].fillna(0).values.reshape(1, -1)
            pred = float(self.models[param].predict(X)[0])
            convention = self.config["module_b"].get("drift_convention", "from_24h")
            base = row["value_24h"] if convention == "from_24h" else row["value_0h"]
            base_hours = 24 if convention == "from_24h" else 0
            drift = pred - base
            drift_rate = drift / (168 - base_hours) if (168 - base_hours) > 0 else 0.0
            predictions.append(
                {
                    "predicted_168h": round(pred, 6),
                    "predicted_drift": round(drift, 6),
                    "drift_rate": round(drift_rate, 8),
                    "actual_168h": row.get("value_168h"),
                }
            )
        return pd.DataFrame(predictions)

    def classify_drift_risk(
        self, predictions: pd.DataFrame, safety_slopes: dict[str, float]
    ) -> pd.DataFrame:
        thresholds = self.config["module_b"]["drift_risk_thresholds"]
        risks = []
        for i, row in predictions.iterrows():
            param = row.get("parameter", "unknown")
            rate = abs(row.get("drift_rate", 0))
            safety = safety_slopes.get(param, 0.1)
            ratio = rate / safety if safety > 1e-12 else 0.0
            if ratio >= thresholds["watch"]:
                risk = "DANGEROUS"
            elif ratio >= thresholds["safe"]:
                risk = "WATCH"
            else:
                risk = "SAFE"
            risks.append({"drift_risk": risk, "drift_ratio": round(ratio, 4)})
        return pd.DataFrame(risks)

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.models, path / "module_b_models.joblib")
        joblib.dump(self.feature_cols, path / "module_b_features.joblib")
        with open(path / "module_b_model_selection.json", "w") as f:
            json.dump(self.selection_results, f, indent=2)

    def load(self, path: Path) -> None:
        self.models = joblib.load(path / "module_b_models.joblib")
        self.feature_cols = joblib.load(path / "module_b_features.joblib")
        sel_path = path / "module_b_model_selection.json"
        if sel_path.exists():
            with open(sel_path) as f:
                self.selection_results = json.load(f)

    def evaluate(self, df: pd.DataFrame, test_ids: set[str]) -> dict[str, Any]:
        test_df = df[df["component_id"].isin(test_ids)].dropna(subset=["value_168h"])
        metrics = {}
        for param in test_df["parameter"].unique():
            if param not in self.models:
                continue
            param_df = test_df[test_df["parameter"] == param]
            X = param_df[self.feature_cols].fillna(0).values
            y = param_df["value_168h"].values
            preds = self.models[param].predict(X)
            metrics[param] = {
                "mae": round(mean_absolute_error(y, preds), 6),
                "rmse": round(float(np.sqrt(mean_squared_error(y, preds))), 6),
                "r2": round(r2_score(y, preds), 6),
            }
        return metrics
