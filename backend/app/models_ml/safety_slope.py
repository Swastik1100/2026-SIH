"""Safety slope computation from healthy population + spec headroom."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_safety_slopes(
    df: pd.DataFrame, config: dict[str, Any], healthy_labels: set[str] | None = None
) -> dict[str, float]:
    """
    Compute per-parameter safety slope as the tighter of:
    (a) percentile of healthy-population observed slopes
    (b) spec-headroom-derived bound
    """
    cfg = config["safety_slope"]
    percentile = cfg["healthy_percentile"]
    horizon = cfg["horizon_hours"]
    use_headroom = cfg.get("use_spec_headroom", True)
    headroom_frac = cfg.get("spec_headroom_fraction", 0.8)

    if healthy_labels is None:
        healthy_labels = {"healthy", "noisy_healthy"}

    healthy_df = df[df["label"].isin(healthy_labels)]
    slopes: dict[str, float] = {}

    for param in df["parameter"].unique():
        param_df = healthy_df[healthy_df["parameter"] == param]
        if len(param_df) == 0:
            slopes[param] = 0.01
            continue

        observed_slopes = (param_df["value_168h"] - param_df["value_0h"]) / horizon
        empirical_slope = float(np.percentile(observed_slopes.abs(), percentile))

        if use_headroom:
            margins = param_df["spec_max"] - param_df["value_96h"]
            headroom_slopes = (margins * headroom_frac) / (horizon - 96)
            spec_slope = float(np.median(headroom_slopes.clip(lower=0)))
            final_slope = min(empirical_slope, spec_slope) if spec_slope > 0 else empirical_slope
        else:
            final_slope = empirical_slope

        slopes[param] = max(final_slope, 1e-8)
        logger.info(
            "Safety slope %s: empirical=%.6f, final=%.6f",
            param,
            empirical_slope,
            final_slope,
        )

    return slopes
