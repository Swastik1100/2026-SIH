#!/usr/bin/env python3
"""Run demo scenario C001-C006 and print headline C003 story."""

import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_config
from app.data.generator import generate_demo_components
from app.explainability.explain import explain_summary_for_demo
from app.services.pipeline import ScreeningPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    config = get_config()
    demo_df = generate_demo_components(config)
    demo_path = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "demo_components.csv"
    demo_path.parent.mkdir(parents=True, exist_ok=True)
    demo_df.to_csv(demo_path, index=False)

    pipeline = ScreeningPipeline(config)
    models_dir = Path(__file__).resolve().parents[1] / "models"
    if not (models_dir / "module_a_lot_iso.joblib").exists() and not (
        models_dir / "module_a_iso.joblib"
    ).exists():
        logger.info("Models not found — training on full dataset first...")
        full_csv = demo_path.parent / "synthetic_burnin.csv"
        if full_csv.exists():
            full_df = pd.read_csv(full_csv)
        else:
            from app.data.generator import generate_dataset
            full_df = generate_dataset(config)
            full_df.to_csv(full_csv, index=False)
        pipeline.train(full_df)

    pipeline.load_models()
    featured = pipeline.prepare_data(demo_df)
    results = [pipeline.process_row(row) for _, row in featured.iterrows()]

    print("\n" + "=" * 70)
    print("DEMO SCENARIO — Burn-In Anomaly Detection")
    print("=" * 70)

    for comp_id in ["C001", "C002", "C003", "C004", "C005", "C006"]:
        comp_results = [r for r in results if r["component_id"] == comp_id]
        if not comp_results:
            continue
        # Focus on leakage_current for display
        leak = next((r for r in comp_results if r["parameter"] == "leakage_current"), comp_results[0])
        print(f"\n--- {comp_id} ({leak.get('label', '?')}) ---")
        print(f"  Static: {leak['decision']['static_result']}")
        print(f"  Anomaly: {leak['anomaly']['severity']} (score={leak['anomaly']['anomaly_score']:.2f})")
        print(f"  Drift: {leak['drift']['drift_risk']}")
        print(f"  Decision: {leak['decision']['decision']}")
        if comp_id == "C003":
            summary = explain_summary_for_demo(
                {**leak, **leak["measurements"]},
                leak["anomaly"],
                leak["drift"],
                leak["decision"],
            )
            print(f"\n  >>> {summary}".encode("ascii", errors="replace").decode("ascii"))

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
