#!/usr/bin/env python3
"""Compare static-only vs +Module A vs +Module A+B screening."""

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.decision.engine import static_check

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFECT_LABELS = {"static_fail", "latent_defect", "gradual_drift", "sudden_drift"}


def _screening_outcome(decision: str) -> str:
    if decision in ("REJECT", "REVIEW"):
        return "FLAGGED"
    return "PASS"


def run_baseline_comparison(pipeline, df: pd.DataFrame) -> dict:
    train_ids, val_ids, test_ids = pipeline.split_ids(pipeline.featured_df)
    test_df = pipeline.featured_df[pipeline.featured_df["component_id"].isin(test_ids)]

    results_full = [pipeline.process_row(row) for _, row in test_df.iterrows()]

    configs = {
        "static_only": lambda r, row: "FLAGGED" if r["decision"]["static_result"] == "FAIL" else "PASS",
        "static_plus_a": lambda r, row: "FLAGGED"
        if r["decision"]["static_result"] == "FAIL" or r["anomaly"]["severity"] in ("MEDIUM", "HIGH")
        else "PASS",
        "full_system": lambda r, row: _screening_outcome(r["decision"]["decision"]),
    }

    comparison = {}
    for name, fn in configs.items():
        flagged_defects = 0
        latent_caught = 0
        false_negatives = 0
        false_positives = 0
        escaped = 0

        for r, (_, row) in zip(results_full, test_df.iterrows()):
            label = row.get("label", "healthy")
            is_defect = label in DEFECT_LABELS
            is_healthy = label in ("healthy", "noisy_healthy")
            outcome = fn(r, row)

            if is_defect:
                if outcome == "FLAGGED":
                    flagged_defects += 1
                    if label == "latent_defect":
                        latent_caught += 1
                else:
                    false_negatives += 1
                    escaped += 1
            elif is_healthy and outcome == "FLAGGED":
                false_positives += 1

        total_defects = sum(1 for _, row in test_df.iterrows() if row.get("label") in DEFECT_LABELS)
        total_latent = sum(1 for _, row in test_df.iterrows() if row.get("label") == "latent_defect")

        comparison[name] = {
            "defects_detected": flagged_defects,
            "latent_defects_detected": latent_caught,
            "latent_defects_total": total_latent,
            "false_negatives": false_negatives,
            "false_positives": false_positives,
            "escaped_defects": escaped,
            "total_defects": total_defects,
            "detection_rate": round(flagged_defects / total_defects, 4) if total_defects else 0,
        }

    out_path = Path(__file__).resolve().parents[1] / "data" / "processed" / "evaluation_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report = {}
    if out_path.exists():
        with open(out_path) as f:
            report = json.load(f)
    report["baseline_comparison"] = comparison

    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info("Baseline comparison saved")
    for name, stats in comparison.items():
        logger.info("  %s: FN=%d, latent=%d/%d", name, stats["false_negatives"], stats["latent_defects_detected"], stats["latent_defects_total"])

    return comparison
