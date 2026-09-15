"""Module A: Dynamic outlier detection — MAD z-score + Isolation Forest + XGBoost classifier.

Two-stage design for near-zero false negatives:
  Stage 1 (unsupervised): MAD robust z-score + Isolation Forest → anomaly_score
  Stage 2 (supervised):   XGBoost binary classifier trained on labeled data → xgb_prob
  Final flag:             OR-logic — flagged if EITHER stage fires above its threshold
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import LabelEncoder

try:
    from xgboost import XGBClassifier
    _XGB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _XGB_AVAILABLE = False

logger = logging.getLogger(__name__)

# Features used by Isolation Forest (unsupervised, no label needed)
FEATURE_COLS_FOR_IF = [
    "value_0h",
    "value_24h",
    "value_96h",
    "delta_24",
    "delta_96",
    "slope_0_24",
    "slope_24_96",
    "acceleration",
    "robust_z_0h",
    "robust_z_24h",
    "robust_z_96h",
    "margin_to_spec_max",
]

# Extended feature set for supervised XGBoost — uses all available engineered features
FEATURE_COLS_FOR_XGB = [
    "value_0h",
    "value_24h",
    "value_96h",
    "delta_24",
    "delta_96",
    "pct_change_24",
    "pct_change_96",
    "slope_0_24",
    "slope_24_96",
    "acceleration",
    "robust_z_0h",
    "robust_z_24h",
    "robust_z_96h",
    "margin_to_spec_max",
    "margin_to_spec_min",
    "lot_median_0h",
    "lot_mad_0h",
    "lot_median_24h",
    "lot_mad_24h",
    "lot_median_96h",
    "lot_mad_96h",
    "spec_max",
    "spec_min",
]

# Labels considered defective for supervised training
DEFECT_LABELS = {"static_fail", "latent_defect", "gradual_drift", "sudden_drift"}


def _robust_z(value: float, median: float, mad: float) -> float:
    if mad < 1e-12:
        return 0.0
    return 0.6745 * (value - median) / mad


class ModuleAAnomalyDetector:
    """Two-stage anomaly detector combining unsupervised MAD+IF with supervised XGBoost.

    OR-logic ensures near-zero false negatives:
        anomaly_label = (combined_score >= threshold) OR (xgb_prob >= xgb_threshold)
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config["module_a"]
        self.lot_models: dict[tuple[str, str], IsolationForest] = {}
        self.global_models: dict[str, IsolationForest] = {}
        self.lot_stats: dict[tuple[str, str, str], tuple[float, float]] = {}
        self.global_stats: dict[tuple[str, str], tuple[float, float]] = {}
        self.threshold = self.config["anomaly_threshold"]
        self.weights = self.config["score_weights"]
        self.severity_bands = self.config["severity_bands"]
        self.xgb_threshold = self.config.get("xgb_threshold", 0.30)
        self.use_xgb = self.config.get("use_xgb_classifier", True) and _XGB_AVAILABLE

        # XGBoost supervised classifier (per-parameter)
        self.xgb_models: dict[str, Any] = {}
        # Global fallback XGB trained on all parameters
        self.xgb_global: Any = None
        self._xgb_feature_cols: list[str] = FEATURE_COLS_FOR_XGB

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def fit(self, df: pd.DataFrame, train_ids: set[str]) -> None:
        train_df = df[df["component_id"].isin(train_ids)].copy()

        # ── Per-lot stats (training lots only) ─────────────────────────
        for (lot_id, param), group in train_df.groupby(["lot_id", "parameter"]):
            for checkpoint in ["value_0h", "value_24h", "value_96h"]:
                vals = group[checkpoint].dropna()
                if len(vals) == 0:
                    continue
                median = float(vals.median())
                mad = float(np.median(np.abs(vals - median)))
                if mad < 1e-12:
                    mad = float(vals.std()) if len(vals) > 1 else 1e-6
                self.lot_stats[(lot_id, param, checkpoint)] = (median, mad)

        # ── Global fallback stats per parameter/checkpoint ──────────────
        for param in train_df["parameter"].unique():
            param_df = train_df[train_df["parameter"] == param]
            for checkpoint in ["value_0h", "value_24h", "value_96h"]:
                vals = param_df[checkpoint].dropna()
                if len(vals) == 0:
                    continue
                median = float(vals.median())
                mad = float(np.median(np.abs(vals - median)))
                if mad < 1e-12:
                    mad = float(vals.std()) if len(vals) > 1 else 1e-6
                self.global_stats[(param, checkpoint)] = (median, mad)

        # ── Per-lot Isolation Forest ────────────────────────────────────
        for (lot_id, param), group in train_df.groupby(["lot_id", "parameter"]):
            if len(group) < 5:
                continue
            X = group[FEATURE_COLS_FOR_IF].fillna(0).values
            iso = IsolationForest(
                n_estimators=self.config["isolation_forest_n_estimators"],
                contamination=self.config["isolation_forest_contamination"],
                random_state=42,
            )
            iso.fit(X)
            self.lot_models[(lot_id, param)] = iso

        # ── Global IF per parameter ─────────────────────────────────────
        for param in train_df["parameter"].unique():
            param_df = train_df[train_df["parameter"] == param]
            if len(param_df) < 10:
                continue
            X = param_df[FEATURE_COLS_FOR_IF].fillna(0).values
            iso = IsolationForest(
                n_estimators=self.config["isolation_forest_n_estimators"],
                contamination=self.config["isolation_forest_contamination"],
                random_state=42,
            )
            iso.fit(X)
            self.global_models[param] = iso

        # ── XGBoost supervised classifier ──────────────────────────────
        if self.use_xgb and "label" in train_df.columns:
            self._fit_xgb(train_df)
        elif self.use_xgb:
            logger.warning("XGBoost classifier skipped — no 'label' column in training data.")

        logger.info(
            "Module A fitted: %d lot IF models, %d global IF models, %d lot stat keys, XGB=%s",
            len(self.lot_models),
            len(self.global_models),
            len(self.lot_stats),
            "YES" if self.xgb_global is not None or self.xgb_models else "NO",
        )

    def _fit_xgb(self, train_df: pd.DataFrame) -> None:
        """Train XGBoost binary classifiers on labeled data."""
        if not _XGB_AVAILABLE:
            return

        # Determine available feature columns (handle partial feature sets gracefully)
        available_feats = [c for c in self._xgb_feature_cols if c in train_df.columns]
        self._xgb_feature_cols = available_feats

        n_estimators = self.config.get("xgb_n_estimators", 300)
        max_depth = self.config.get("xgb_max_depth", 6)
        learning_rate = self.config.get("xgb_learning_rate", 0.05)

        # ── Per-parameter XGBoost models ───────────────────────────────
        for param in train_df["parameter"].unique():
            param_df = train_df[train_df["parameter"] == param].dropna(
                subset=available_feats, how="all"
            )
            if len(param_df) < 20:
                continue

            X = param_df[available_feats].fillna(0).values
            y = param_df["label"].apply(lambda lbl: 1 if lbl in DEFECT_LABELS else 0).values

            n_defect = y.sum()
            n_healthy = len(y) - n_defect
            if n_defect == 0 or n_healthy == 0:
                continue

            # scale_pos_weight = ratio of negatives to positives → handles class imbalance
            spw = n_healthy / max(n_defect, 1)

            xgb = XGBClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=learning_rate,
                scale_pos_weight=spw,
                subsample=0.8,
                colsample_bytree=0.8,
                use_label_encoder=False,
                eval_metric="logloss",
                random_state=42,
                n_jobs=-1,
            )
            xgb.fit(X, y)
            self.xgb_models[param] = xgb
            logger.info(
                "XGBoost fitted for param=%s | n=%d defects=%d (spw=%.1f)",
                param,
                len(y),
                n_defect,
                spw,
            )

        # ── Global XGBoost fallback (all parameters combined) ──────────
        all_df = train_df.dropna(subset=available_feats, how="all")
        if len(all_df) >= 50:
            X_all = all_df[available_feats].fillna(0).values
            y_all = all_df["label"].apply(lambda lbl: 1 if lbl in DEFECT_LABELS else 0).values
            n_def = y_all.sum()
            n_hlt = len(y_all) - n_def
            if n_def > 0 and n_hlt > 0:
                spw_global = n_hlt / max(n_def, 1)
                xgb_global = XGBClassifier(
                    n_estimators=n_estimators,
                    max_depth=max_depth,
                    learning_rate=learning_rate,
                    scale_pos_weight=spw_global,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    use_label_encoder=False,
                    eval_metric="logloss",
                    random_state=42,
                    n_jobs=-1,
                )
                xgb_global.fit(X_all, y_all)
                self.xgb_global = xgb_global
                logger.info(
                    "XGBoost global model fitted | n=%d defects=%d", len(y_all), n_def
                )

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _get_stat(self, lot_id: str, param: str, checkpoint: str) -> tuple[float, float]:
        key = (lot_id, param, checkpoint)
        if key in self.lot_stats:
            return self.lot_stats[key]
        return self.global_stats.get((param, checkpoint), (0.0, 1.0))

    def _mad_score(self, row: pd.Series) -> tuple[float, dict[str, float]]:
        z_scores = {}
        lot_id = row["lot_id"]
        param = row["parameter"]
        for suffix, checkpoint in [("0h", "value_0h"), ("24h", "value_24h"), ("96h", "value_96h")]:
            col = f"robust_z_{suffix}"
            if col in row.index and pd.notna(row[col]):
                z_scores[col] = abs(float(row[col]))
            elif checkpoint in row.index and pd.notna(row[checkpoint]):
                median, mad = self._get_stat(lot_id, param, checkpoint)
                z_scores[col] = abs(_robust_z(float(row[checkpoint]), median, mad))

        max_z = max(z_scores.values()) if z_scores else 0.0
        normalized = min(max_z / self.config["mad_z_threshold"], 1.0)
        return normalized, z_scores

    def _iso_score(self, row: pd.Series) -> float:
        X = row[FEATURE_COLS_FOR_IF].fillna(0).values.reshape(1, -1)
        key = (row["lot_id"], row["parameter"])
        if key in self.lot_models:
            score = -self.lot_models[key].score_samples(X)[0]
        elif row["parameter"] in self.global_models:
            score = -self.global_models[row["parameter"]].score_samples(X)[0]
        else:
            return 0.0
        return float(min(max(score / 0.5, 0.0), 1.0))

    def _xgb_score(self, row: pd.Series) -> float:
        """Return XGBoost defect probability [0, 1]."""
        if not self.use_xgb:
            return 0.0

        available = [c for c in self._xgb_feature_cols if c in row.index]
        if not available:
            return 0.0

        X = row[available].fillna(0).values.reshape(1, -1)
        param = row["parameter"]

        model = self.xgb_models.get(param) or self.xgb_global
        if model is None:
            return 0.0

        prob = float(model.predict_proba(X)[0][1])
        return prob

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def score_row(self, row: pd.Series) -> dict[str, Any]:
        mad_norm, z_contrib = self._mad_score(row)
        iso_norm = self._iso_score(row)
        xgb_prob = self._xgb_score(row)

        # Weighted unsupervised combined score
        w_mad = self.weights.get("mad", 0.45)
        w_iso = self.weights.get("isolation_forest", 0.35)
        w_xgb = self.weights.get("xgb", 0.20)

        # Normalise weights so they always sum to 1 even if xgb is off
        if not self.use_xgb or (self.xgb_global is None and not self.xgb_models):
            total_w = w_mad + w_iso
            w_mad /= total_w
            w_iso /= total_w
            w_xgb = 0.0

        combined = w_mad * mad_norm + w_iso * iso_norm + w_xgb * xgb_prob
        combined = min(combined, 1.0)

        # OR-logic: flag if EITHER the combined score OR the XGBoost probability fires
        xgb_flag = xgb_prob >= self.xgb_threshold if self.use_xgb else False
        score_flag = combined >= self.threshold
        anomaly_label = score_flag or xgb_flag

        if combined >= self.severity_bands["high"] or xgb_prob >= 0.70:
            severity = "HIGH"
        elif combined >= self.severity_bands["medium"] or xgb_prob >= 0.50:
            severity = "MEDIUM"
        elif anomaly_label:
            severity = "MEDIUM"  # Caught only by XGBoost — still elevate
        else:
            severity = "LOW"

        top_features = sorted(z_contrib.items(), key=lambda x: -x[1])[:3]
        contributing = [f"{k}: z={v:.2f}" for k, v in top_features]
        if xgb_flag and not score_flag:
            contributing.insert(0, f"xgb_classifier: prob={xgb_prob:.3f}")

        return {
            "robust_z_score": mad_norm,
            "isolation_forest_score": iso_norm,
            "xgb_score": round(xgb_prob, 4),
            "anomaly_score": round(combined, 4),
            "anomaly_label": anomaly_label,
            "xgb_triggered": xgb_flag,
            "severity": severity,
            "contributing_features": contributing,
        }

    def score_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        results = [self.score_row(row) for _, row in df.iterrows()]
        return pd.DataFrame(results)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.lot_models, path / "module_a_lot_iso.joblib")
        joblib.dump(self.global_models, path / "module_a_global_iso.joblib")
        joblib.dump(self.lot_stats, path / "module_a_lot_stats.joblib")
        joblib.dump(self.global_stats, path / "module_a_global_stats.joblib")
        # XGBoost models
        joblib.dump(self.xgb_models, path / "module_a_xgb_models.joblib")
        joblib.dump(self.xgb_global, path / "module_a_xgb_global.joblib")
        joblib.dump(self._xgb_feature_cols, path / "module_a_xgb_features.joblib")
        with open(path / "module_a_config.json", "w") as f:
            json.dump(self.config, f)

    def load(self, path: Path) -> None:
        # Isolation Forest models
        if (path / "module_a_lot_iso.joblib").exists():
            self.lot_models = joblib.load(path / "module_a_lot_iso.joblib")
            self.global_models = joblib.load(path / "module_a_global_iso.joblib")
            self.lot_stats = joblib.load(path / "module_a_lot_stats.joblib")
            self.global_stats = joblib.load(path / "module_a_global_stats.joblib")
        else:
            # Backward compat with older single-file format
            self.lot_models = joblib.load(path / "module_a_iso.joblib")
            self.lot_stats = joblib.load(path / "module_a_lot_stats.joblib")
            self.global_stats = {}

        # XGBoost models (optional — graceful fallback if not present)
        xgb_path = path / "module_a_xgb_models.joblib"
        if xgb_path.exists() and _XGB_AVAILABLE:
            self.xgb_models = joblib.load(xgb_path)
            global_xgb_path = path / "module_a_xgb_global.joblib"
            if global_xgb_path.exists():
                self.xgb_global = joblib.load(global_xgb_path)
            feat_path = path / "module_a_xgb_features.joblib"
            if feat_path.exists():
                self._xgb_feature_cols = joblib.load(feat_path)
            logger.info(
                "Loaded %d per-param XGB models + global=%s",
                len(self.xgb_models),
                self.xgb_global is not None,
            )
        else:
            logger.info("No XGBoost models found on disk — running in unsupervised-only mode.")
