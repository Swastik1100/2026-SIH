#!/usr/bin/env python3
"""Evaluate Module A, Module B, and screening performance."""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFECT_LABELS = {"static_fail", "latent_defect", "gradual_drift", "sudden_drift"}


def run_evaluation(pipeline, df: pd.DataFrame) -> dict:
    train_ids, val_ids, test_ids = pipeline.split_ids(pipeline.prepare_data(df))
    featured = pipeline.featured_df
    test_df = featured[featured["component_id"].isin(test_ids)]

    # Module A evaluation
    anomaly_scores = pipeline.module_a.score_dataframe(test_df)
    y_true = test_df["label"].apply(lambda x: x in DEFECT_LABELS).astype(int).values
    y_score = anomaly_scores["anomaly_score"].values
    y_pred = anomaly_scores["anomaly_label"].astype(int).values

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    module_a_metrics = {
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "false_negative_rate": round(fn / (fn + tp) if (fn + tp) > 0 else 0, 4),
        "false_positive_rate": round(fp / (fp + tn) if (fp + tn) > 0 else 0, 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }

    # XGBoost breakdown — shows how many defects were caught ONLY by the supervised classifier
    if "xgb_triggered" in anomaly_scores.columns:
        xgb_triggered = anomaly_scores["xgb_triggered"].astype(int).values
        score_only_pred = (
            anomaly_scores["anomaly_score"] >= pipeline.module_a.threshold
        ).astype(int).values
        xgb_only_saves = int(
            ((xgb_triggered == 1) & (score_only_pred == 0) & (y_true == 1)).sum()
        )
        module_a_metrics["xgb_triggered_count"] = int(xgb_triggered.sum())
        module_a_metrics["xgb_only_true_positives"] = xgb_only_saves

    if "xgb_score" in anomaly_scores.columns and y_true.sum() > 0:
        module_a_metrics["avg_xgb_score_defects"] = round(
            float(anomaly_scores.loc[y_true == 1, "xgb_score"].mean()), 4
        )

    try:
        module_a_metrics["roc_auc"] = round(roc_auc_score(y_true, y_score), 4)
        module_a_metrics["pr_auc"] = round(average_precision_score(y_true, y_score), 4)
    except ValueError:
        pass

    # Module B evaluation
    module_b_metrics = pipeline.module_b.evaluate(featured, test_ids)
    module_b_metrics["model_selection"] = pipeline.module_b.selection_results

    # Screening-level
    results = [pipeline.process_row(row) for _, row in test_df.iterrows()]
    latent_caught = sum(
        1 for r in results if r.get("label") == "latent_defect" and r["decision"]["decision"] in ("REJECT", "REVIEW")
    )
    latent_total = sum(1 for r in results if r.get("label") == "latent_defect")
    healthy_fp = sum(
        1 for r in results if r.get("label") in ("healthy", "noisy_healthy") and r["decision"]["decision"] in ("REJECT", "REVIEW")
    )

    report = {
        "module_a": module_a_metrics,
        "module_b": module_b_metrics,
        "screening": {
            "latent_defects_caught": latent_caught,
            "latent_defects_total": latent_total,
            "latent_capture_rate": round(latent_caught / latent_total, 4) if latent_total else 0,
            "healthy_false_positives": healthy_fp,
            "test_components": len(test_ids),
        },
    }

    out_path = Path(__file__).resolve().parents[1] / "data" / "processed" / "evaluation_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Merge with baseline if exists
    if out_path.exists():
        with open(out_path) as f:
            existing = json.load(f)
        existing.update(report)
        report = existing

    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Evaluation report saved to %s", out_path)
    pipeline.evaluation_report = report
    return report


if __name__ == "__main__":
    from app.core.config import get_config
    from app.services.pipeline import ScreeningPipeline

    config = get_config()
    df = pd.read_csv(Path(__file__).resolve().parents[1] / "data" / "synthetic" / "synthetic_burnin.csv")
    pipeline = ScreeningPipeline(config)
    pipeline.load_models()
    pipeline.featured_df = pipeline.prepare_data(df)
    run_evaluation(pipeline, df)
