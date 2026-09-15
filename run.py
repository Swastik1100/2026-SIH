#!/usr/bin/env python3
"""
BurnSight AI — One-shot pipeline runner.

Usage:
    python run.py                  # Generate data, train, evaluate, start API
    python run.py --pipeline-only  # Run pipeline only (no API server)
    python run.py --skip-generate  # Skip data generation (reuse existing)
    python run.py --demo-only      # Run demo scenario C001-C006 and print report

This script:
  1. Generates synthetic burn-in data (unless --skip-generate)
  2. Trains Module A (anomaly detection) and Module B (drift prediction)
  3. Computes safety slopes
  4. Screens full dataset + demo components and persists to DB
  5. Runs evaluation (Module A metrics, Module B metrics)
  6. Runs baseline comparison (static vs +A vs +A+B)
  7. Starts FastAPI server on port 8000 (unless --pipeline-only)
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# Set root to project repo root
REPO_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = REPO_ROOT / "backend"

# Ensure backend is importable
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("burnsight")


def run_pipeline(skip_generate: bool = False) -> None:
    """Run full ML pipeline: generate → train → evaluate → screen."""
    logger.info("=" * 60)
    logger.info("BurnSight AI — Full Pipeline Run")
    logger.info("=" * 60)

    from app.core.config import get_config
    from app.data.generator import generate_dataset, generate_demo_components
    from app.services.pipeline import ScreeningPipeline
    import pandas as pd

    config = get_config()
    data_dir = BACKEND_ROOT / "data" / "synthetic"
    data_dir.mkdir(parents=True, exist_ok=True)

    csv_path = data_dir / "synthetic_burnin.csv"

    # Step 1: Generate data
    if not skip_generate or not csv_path.exists():
        logger.info("Step 1/6: Generating synthetic dataset...")
        df = generate_dataset(config)
        df.to_csv(csv_path, index=False)
        logger.info("  → %d rows, %d unique components saved to %s",
                    len(df), df["component_id"].nunique(), csv_path)
    else:
        logger.info("Step 1/6: Loading existing dataset from %s", csv_path)
        df = pd.read_csv(csv_path)
        logger.info("  → %d rows loaded", len(df))

    # Step 2: Generate demo set
    logger.info("Step 2/6: Generating demo components (C001–C006)...")
    demo_df = generate_demo_components(config)
    demo_path = data_dir / "demo_components.csv"
    demo_df.to_csv(demo_path, index=False)
    logger.info("  → %d demo rows saved", len(demo_df))

    # Step 3: Train
    logger.info("Step 3/6: Training pipeline (Module A + Module B + safety slopes)...")
    pipeline = ScreeningPipeline(config)
    pipeline.train(df)
    logger.info("  → Training complete. Models saved to %s", BACKEND_ROOT / "models")

    # Step 4: Screen full dataset
    logger.info("Step 4/6: Screening full synthetic dataset...")
    pipeline.screen_dataframe(df, persist=True)
    logger.info("  → Screening complete, results persisted to DB")

    # Step 5: Screen demo components
    logger.info("Step 5/6: Screening demo components...")
    pipeline.screen_dataframe(demo_df, persist=True)
    logger.info("  → Demo screening complete")

    # Step 6: Evaluate
    logger.info("Step 6/6: Running evaluation and baseline comparison...")
    sys.path.insert(0, str(BACKEND_ROOT / "scripts"))
    from evaluate import run_evaluation
    from compare_baselines import run_baseline_comparison

    report = run_evaluation(pipeline, df)
    comparison = run_baseline_comparison(pipeline, df)

    # Print summary
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE — Summary")
    logger.info("=" * 60)
    ma = report.get("module_a", {})
    logger.info("Module A: Precision=%.3f Recall=%.3f F1=%.3f FNR=%.3f ROC-AUC=%.3f",
                ma.get("precision", 0), ma.get("recall", 0), ma.get("f1", 0),
                ma.get("false_negative_rate", 0), ma.get("roc_auc", 0))

    for name, stats in comparison.items():
        logger.info("  [%s] Latent=%d/%d  FN=%d  Escaped=%d  DetRate=%.1f%%",
                    name,
                    stats["latent_defects_detected"], stats["latent_defects_total"],
                    stats["false_negatives"], stats["escaped_defects"],
                    stats["detection_rate"] * 100)

    logger.info("Evaluation report: %s", BACKEND_ROOT / "data" / "processed" / "evaluation_report.json")


def run_demo() -> None:
    """Run the C001–C006 demo scenario and print the C003 story."""
    script = BACKEND_ROOT / "scripts" / "run_demo.py"
    subprocess.run([sys.executable, str(script)], check=True, cwd=str(BACKEND_ROOT))


def start_api() -> None:
    """Start the FastAPI server (blocking)."""
    logger.info("=" * 60)
    logger.info("Starting FastAPI server on http://localhost:8000")
    logger.info("API docs: http://localhost:8000/docs")
    logger.info("Frontend (dev): npm run dev  →  http://localhost:5173")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=str(BACKEND_ROOT),
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BurnSight AI — One-shot pipeline + API runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--pipeline-only", action="store_true",
                        help="Run pipeline only; do not start the API server")
    parser.add_argument("--skip-generate", action="store_true",
                        help="Skip dataset generation (reuse existing CSV)")
    parser.add_argument("--demo-only", action="store_true",
                        help="Run demo scenario C001-C006 and exit")
    parser.add_argument("--api-only", action="store_true",
                        help="Start API server only (assumes pipeline already run)")
    args = parser.parse_args()

    if args.demo_only:
        run_demo()
        return

    if args.api_only:
        start_api()
        return

    run_pipeline(skip_generate=args.skip_generate)

    if not args.pipeline_only:
        start_api()


if __name__ == "__main__":
    main()
