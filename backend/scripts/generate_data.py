#!/usr/bin/env python3
"""Generate synthetic burn-in dataset."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_config
from app.data.generator import generate_dataset, generate_demo_components

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--demo", action="store_true", help="Generate demo set only")
    args = parser.parse_args()

    config = get_config()
    seed = args.seed or config.get("random_seed", 42)
    output_dir = Path(__file__).resolve().parents[1] / config["dataset"]["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        df = generate_demo_components(config)
        out = output_dir / "demo_components.csv"
    else:
        df = generate_dataset(config, seed=seed)
        out = output_dir / "synthetic_burnin.csv"

    df.to_csv(out, index=False)
    logger.info("Saved %d rows to %s", len(df), out)
    print(f"Generated {len(df)} rows -> {out}")


if __name__ == "__main__":
    main()
