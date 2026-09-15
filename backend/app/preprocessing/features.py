"""Leakage-free feature engineering for Module A and Module B."""

from __future__ import annotations

import numpy as np
import pandas as pd

# Module B input features — explicitly excludes any 168h-derived quantities
MODULE_B_INPUT_FEATURES = [
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
    "lot_median_0h",
    "lot_mad_0h",
    "robust_z_0h",
    "lot_median_24h",
    "lot_mad_24h",
    "robust_z_24h",
    "lot_median_96h",
    "lot_mad_96h",
    "robust_z_96h",
    "margin_to_spec_max",
    "margin_to_spec_min",
    "spec_max",
    "spec_min",
]

# Features that must NEVER appear in Module B inputs
FORBIDDEN_MODULE_B_FEATURES = [
    "value_168h",
    "delta_168",
    "slope_96_168",
    "pct_change_168",
    "observed_drift_168",
]


def _robust_z(value: float, median: float, mad: float) -> float:
    if mad < 1e-12:
        return 0.0
    return 0.6745 * (value - median) / mad


def compute_lot_stats(
    df: pd.DataFrame,
    train_component_ids: set[str] | None = None,
    use_batch_for_unknown_lots: bool = False,
) -> dict[tuple[str, str, str], tuple[float, float]]:
    """Compute lot median and MAD per (lot_id, parameter, checkpoint)."""
    stats: dict[tuple[str, str, str], tuple[float, float]] = {}
    work = df if train_component_ids is None else df[df["component_id"].isin(train_component_ids)]

    for (lot_id, param), group in work.groupby(["lot_id", "parameter"]):
        for checkpoint in ["value_0h", "value_24h", "value_96h"]:
            vals = group[checkpoint].dropna()
            if len(vals) == 0:
                continue
            median = float(vals.median())
            mad = float(np.median(np.abs(vals - median)))
            if mad < 1e-12:
                mad = float(vals.std()) if len(vals) > 1 else 1e-6
            stats[(lot_id, param, checkpoint)] = (median, mad)

    # Global fallback per parameter/checkpoint from training data
    for param in work["parameter"].unique():
        param_df = work[work["parameter"] == param]
        for checkpoint in ["value_0h", "value_24h", "value_96h"]:
            vals = param_df[checkpoint].dropna()
            if len(vals) == 0:
                continue
            median = float(vals.median())
            mad = float(np.median(np.abs(vals - median)))
            if mad < 1e-12:
                mad = float(vals.std()) if len(vals) > 1 else 1e-6
            stats[("__global__", param, checkpoint)] = (median, mad)

    # For inference batches (e.g. demo lot), compute stats from full batch
    if use_batch_for_unknown_lots:
        for (lot_id, param), group in df.groupby(["lot_id", "parameter"]):
            for checkpoint in ["value_0h", "value_24h", "value_96h"]:
                key = (lot_id, param, checkpoint)
                if key in stats:
                    continue
                vals = group[checkpoint].dropna()
                if len(vals) < 2:
                    continue
                median = float(vals.median())
                mad = float(np.median(np.abs(vals - median)))
                if mad < 1e-12:
                    mad = float(vals.std()) if len(vals) > 1 else 1e-6
                stats[key] = (median, mad)

    return stats


def engineer_features(
    df: pd.DataFrame, lot_stats: dict[tuple[str, str, str], tuple[float, float]] | None = None
) -> pd.DataFrame:
    df = df.copy()
    if lot_stats is None:
        lot_stats = compute_lot_stats(df)

    df["delta_24"] = df["value_24h"] - df["value_0h"]
    df["delta_96"] = df["value_96h"] - df["value_24h"]
    df["delta_168"] = df["value_168h"] - df["value_96h"]  # eval only

    df["pct_change_24"] = np.where(
        df["value_0h"].abs() > 1e-12,
        (df["delta_24"] / df["value_0h"]) * 100,
        0.0,
    )
    df["pct_change_96"] = np.where(
        df["value_24h"].abs() > 1e-12,
        (df["delta_96"] / df["value_24h"].replace(0, np.nan)) * 100,
        0.0,
    )
    df["pct_change_96"] = df["pct_change_96"].fillna(0.0)

    df["slope_0_24"] = df["delta_24"] / 24.0
    df["slope_24_96"] = df["delta_96"] / 72.0
    df["slope_96_168"] = df["delta_168"] / 72.0  # eval only
    df["acceleration"] = (df["slope_24_96"] - df["slope_0_24"]) / 72.0

    df["margin_to_spec_max"] = df["spec_max"] - df[["value_0h", "value_24h", "value_96h"]].max(axis=1)
    df["margin_to_spec_min"] = df[["value_0h", "value_24h", "value_96h"]].min(axis=1) - df["spec_min"]

    for checkpoint in ["value_0h", "value_24h", "value_96h"]:
        suffix = checkpoint.replace("value_", "")
        medians, mads, zscores = [], [], []
        for _, row in df.iterrows():
            key = (row["lot_id"], row["parameter"], checkpoint)
            if key in lot_stats:
                med, mad = lot_stats[key]
            else:
                gkey = ("__global__", row["parameter"], checkpoint)
                med, mad = lot_stats.get(gkey, (np.nan, 1e-6))
            medians.append(med)
            mads.append(mad)
            zscores.append(_robust_z(row[checkpoint], med, mad) if pd.notna(row[checkpoint]) else 0.0)
        df[f"lot_median_{suffix}"] = medians
        df[f"lot_mad_{suffix}"] = mads
        df[f"robust_z_{suffix}"] = zscores

    return df


def get_module_b_feature_columns(use_96h: bool = True) -> list[str]:
    cols = list(MODULE_B_INPUT_FEATURES)
    if not use_96h:
        cols = [c for c in cols if "96" not in c]
    for forbidden in FORBIDDEN_MODULE_B_FEATURES:
        assert forbidden not in cols, f"Leakage: {forbidden} in Module B features"
    return cols


def assert_no_leakage(feature_columns: list[str]) -> None:
    for forbidden in FORBIDDEN_MODULE_B_FEATURES:
        if forbidden in feature_columns:
            raise AssertionError(f"Module B feature leakage detected: {forbidden}")
