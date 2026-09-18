#!/usr/bin/env python3
"""Full pipeline: generate -> train -> evaluate -> screen -> persist."""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Ensure the backend directory and scripts directory are on the path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from app.core.config import get_config
from app.data.generator import generate_dataset, generate_demo_components
from app.services.pipeline import ScreeningPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-generate", action="store_true")
    args = parser.parse_args()

    backend_root = Path(__file__).resolve().parents[1]
    config = get_config()
    data_dir = backend_root / "data" / "synthetic"
    data_dir.mkdir(parents=True, exist_ok=True)

    csv_path = data_dir / "synthetic_burnin.csv"
    if not args.skip_generate or not csv_path.exists():
        logger.info("Generating synthetic dataset...")
        df = generate_dataset(config)
        df.to_csv(csv_path, index=False)
    else:
        df = pd.read_csv(csv_path)

    demo_df = generate_demo_components(config)
    demo_path = data_dir / "demo_components.csv"
    demo_df.to_csv(demo_path, index=False)

    pipeline = ScreeningPipeline(config)
    logger.info("Training pipeline...")
    pipeline.train(df)

    logger.info("Screening full dataset...")
    pipeline.screen_dataframe(df, persist=True)

    logger.info("Screening demo components...")
    pipeline.screen_dataframe(demo_df, persist=True)

    # Run evaluation
    from evaluate import run_evaluation
    from compare_baselines import run_baseline_comparison

    run_evaluation(pipeline, df)
    run_baseline_comparison(pipeline, df)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
