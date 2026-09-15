"""End-to-end screening pipeline orchestration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import get_config
from app.data.database import ScreeningResult, get_session_factory, init_db
from app.decision.engine import decide, load_decision_rules
from app.explainability.explain import explain_component
from app.models_ml.module_a_anomaly import ModuleAAnomalyDetector
from app.models_ml.module_b_drift import ModuleBDriftPredictor
from app.models_ml.safety_slope import compute_safety_slopes
from app.preprocessing.cleaning import clean_dataset
from app.preprocessing.features import compute_lot_stats, engineer_features
from app.preprocessing.validation import detect_invalid_rows, validate_schema

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


class ScreeningPipeline:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or get_config()
        self.module_a = ModuleAAnomalyDetector(self.config)
        self.module_b = ModuleBDriftPredictor(self.config)
        self.safety_slopes: dict[str, float] = {}
        self.rules = load_decision_rules(self.config)
        self.default_decision = "REVIEW"
        self.default_reason = "Mixed signals — manual QA review recommended."
        self._trained = False
        self.featured_df: pd.DataFrame | None = None
        self.evaluation_report: dict[str, Any] = {}

    def split_ids(self, df: pd.DataFrame) -> tuple[set[str], set[str], set[str]]:
        eval_cfg = self.config.get("evaluation", {})
        test_frac = eval_cfg.get("test_fraction", 0.2)
        val_frac = eval_cfg.get("val_fraction", 0.15)

        component_ids = df["component_id"].unique()
        if eval_cfg.get("split_by_lot", True):
            lots = df.groupby("lot_id")["component_id"].apply(lambda x: list(x.unique()))
            lot_ids = list(lots.index)
            n_test = max(1, int(len(lot_ids) * test_frac))
            n_val = max(1, int(len(lot_ids) * val_frac))
            test_lots = set(lot_ids[-n_test:])
            val_lots = set(lot_ids[-(n_test + n_val) : -n_test])
            train_lots = set(lot_ids[: -(n_test + n_val)])

            train_ids = set(df[df["lot_id"].isin(train_lots)]["component_id"].unique())
            val_ids = set(df[df["lot_id"].isin(val_lots)]["component_id"].unique())
            test_ids = set(df[df["lot_id"].isin(test_lots)]["component_id"].unique())
        else:
            n = len(component_ids)
            n_test = int(n * test_frac)
            n_val = int(n * val_frac)
            train_ids = set(component_ids[: n - n_test - n_val])
            val_ids = set(component_ids[n - n_test - n_val : n - n_test])
            test_ids = set(component_ids[n - n_test :])

        return train_ids, val_ids, test_ids

    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        validate_schema(df)
        invalid = detect_invalid_rows(df)
        processed_dir = Path(__file__).resolve().parents[2] / "data" / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        if not invalid.empty:
            invalid.to_csv(processed_dir / "rejected_records.csv", index=False)
        cleaned = clean_dataset(df, invalid)
        train_ids, _, _ = self.split_ids(cleaned)
        lot_stats = compute_lot_stats(cleaned, train_ids)
        featured = engineer_features(cleaned, lot_stats)
        self.featured_df = featured
        return featured

    def train(self, df: pd.DataFrame) -> None:
        featured = self.prepare_data(df)
        train_ids, val_ids, test_ids = self.split_ids(featured)

        self.module_a.fit(featured, train_ids)
        self.module_b.select_and_train(featured, train_ids)
        self.safety_slopes = compute_safety_slopes(featured, self.config)

        self.module_a.save(MODELS_DIR)
        self.module_b.save(MODELS_DIR)
        with open(MODELS_DIR / "safety_slopes.json", "w") as f:
            json.dump(self.safety_slopes, f)

        self._trained = True
        logger.info("Pipeline trained. Train=%d, Val=%d, Test=%d components", 
                    len(train_ids), len(val_ids), len(test_ids))

    def load_models(self) -> None:
        self.module_a.load(MODELS_DIR)
        self.module_b.load(MODELS_DIR)
        slopes_path = MODELS_DIR / "safety_slopes.json"
        if slopes_path.exists():
            with open(slopes_path) as f:
                self.safety_slopes = json.load(f)
        self._trained = True

    def process_row(self, row: pd.Series) -> dict[str, Any]:
        anomaly = self.module_a.score_row(row)
        pred_df = self.module_b.predict(pd.DataFrame([row]))
        pred_row = pred_df.iloc[0].to_dict()
        pred_row["parameter"] = row["parameter"]
        risk_df = self.module_b.classify_drift_risk(
            pd.DataFrame([{**pred_row, "parameter": row["parameter"]}]),
            self.safety_slopes,
        )
        drift = {**pred_row, **risk_df.iloc[0].to_dict()}
        row_dict = row.to_dict()
        decision = decide(
            row_dict, anomaly, drift, self.rules, self.default_decision, self.default_reason
        )
        explanation = explain_component(row_dict, anomaly, drift, decision, self.safety_slopes)
        return {
            "component_id": row["component_id"],
            "lot_id": row["lot_id"],
            "parameter": row["parameter"],
            "spec_min": row.get("spec_min"),
            "spec_max": row.get("spec_max"),
            "measurements": {
                "value_0h": row.get("value_0h"),
                "value_24h": row.get("value_24h"),
                "value_96h": row.get("value_96h"),
                "value_168h": row.get("value_168h"),
            },
            "anomaly": anomaly,
            "drift": drift,
            "decision": decision,
            "explanation": explanation,
            "label": row.get("label"),
        }

    def screen_dataframe(self, df: pd.DataFrame, persist: bool = True) -> list[dict[str, Any]]:
        if not self._trained:
            self.load_models()

        train_ids, _, _ = self.split_ids(df) if "label" in df.columns else (set(), set(), set())
        lot_stats = compute_lot_stats(
            self.featured_df if self.featured_df is not None and train_ids else df,
            train_ids if train_ids else None,
        )
        # For new lots (demo), add batch-computed stats
        batch_stats = compute_lot_stats(df, use_batch_for_unknown_lots=True)
        lot_stats.update({k: v for k, v in batch_stats.items() if k not in lot_stats})
        featured = engineer_features(df, lot_stats)
        results = [self.process_row(row) for _, row in featured.iterrows()]

        if persist:
            self._persist_results(results)
        return results

    def _persist_results(self, results: list[dict[str, Any]]) -> None:
        init_db()
        Session = get_session_factory()
        session = Session()
        try:
            for r in results:
                rec = ScreeningResult(
                    component_id=r["component_id"],
                    lot_id=r["lot_id"],
                    parameter=r["parameter"],
                    value_0h=r["measurements"].get("value_0h"),
                    value_24h=r["measurements"].get("value_24h"),
                    value_96h=r["measurements"].get("value_96h"),
                    value_168h=r["measurements"].get("value_168h"),
                    spec_min=r.get("spec_min"),
                    spec_max=r.get("spec_max"),
                    static_result=r["decision"]["static_result"],
                    anomaly_score=r["anomaly"]["anomaly_score"],
                    anomaly_severity=r["anomaly"]["severity"],
                    predicted_168h=r["drift"].get("predicted_168h"),
                    drift_risk=r["drift"].get("drift_risk"),
                    drift_rate=r["drift"].get("drift_rate"),
                    final_decision=r["decision"]["decision"],
                    explanation=r["explanation"],
                    label=r.get("label"),
                )
                session.add(rec)
            session.commit()
        finally:
            session.close()


_pipeline: ScreeningPipeline | None = None


def get_pipeline() -> ScreeningPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ScreeningPipeline()
        models_exist = (MODELS_DIR / "module_a_lot_iso.joblib").exists() or (
            MODELS_DIR / "module_a_iso.joblib"
        ).exists()
        if models_exist:
            _pipeline.load_models()
    return _pipeline
