"""Synthetic burn-in / ESS dataset generator."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

CHECKPOINTS = ["value_0h", "value_24h", "value_96h", "value_168h"]
HOURS = [0, 24, 96, 168]
PARAMETERS = ["iddq", "leakage_current", "propagation_delay"]


def _pick_label(rng: np.random.Generator, dist: dict[str, float]) -> str:
    labels = list(dist.keys())
    probs = np.array([dist[k] for k in labels], dtype=float)
    probs /= probs.sum()
    return str(rng.choice(labels, p=probs))


def _trajectory_healthy(
    baseline: float, noise: float, rng: np.random.Generator
) -> list[float]:
    drift = rng.uniform(-0.02, 0.05) * baseline
    values = [baseline]
    for _ in range(3):
        values.append(values[-1] + drift + rng.normal(0, noise))
    return values


def _trajectory_static_fail(
    baseline: float,
    spec_min: float,
    spec_max: float,
    noise: float,
    rng: np.random.Generator,
) -> list[float]:
    values = _trajectory_healthy(baseline, noise, rng)
    fail_at = rng.integers(1, 4)
    if rng.random() < 0.5:
        values[fail_at] = spec_max * rng.uniform(1.05, 1.3)
    else:
        # For parameters with spec_min=0 (e.g. leakage_current), offset below zero
        offset = max(abs(spec_min) * 0.5, 0.5)
        values[fail_at] = spec_min - rng.uniform(offset * 0.5, offset * 1.5)
    return values


def _trajectory_latent_defect(
    lot_median: float,
    spec_max: float,
    noise: float,
    rng: np.random.Generator,
) -> list[float]:
    # Stays below spec but drifts far above lot median by 168h
    start = lot_median * rng.uniform(0.9, 1.2)
    target = spec_max * rng.uniform(0.85, 0.92)
    values = [start]
    for i in range(1, 4):
        frac = i / 3
        val = start + (target - start) * (frac**1.5) + rng.normal(0, noise)
        values.append(min(val, spec_max * 0.98))
    return values


def _trajectory_gradual_drift(
    baseline: float, spec_max: float, noise: float, rng: np.random.Generator
) -> list[float]:
    slope = (spec_max * 0.7 - baseline) / 168.0
    values = []
    for h in HOURS:
        values.append(baseline + slope * h + rng.normal(0, noise))
    return values


def _trajectory_sudden_drift(
    baseline: float, spec_max: float, noise: float, rng: np.random.Generator
) -> list[float]:
    values = [baseline + rng.normal(0, noise) for _ in range(3)]
    jump = baseline + (spec_max * 0.6 - baseline) * rng.uniform(0.8, 1.0)
    values.append(jump + rng.normal(0, noise))
    return values


def _trajectory_noisy_healthy(
    lot_median: float, spec_max: float, noise: float, rng: np.random.Generator
) -> list[float]:
    # High baseline but stable — should NOT be flagged
    baseline = lot_median * rng.uniform(1.8, 2.5)
    if baseline > spec_max * 0.5:
        baseline = lot_median * 1.5
    return _trajectory_healthy(baseline, noise * 2, rng)


def generate_component_rows(
    component_id: str,
    lot_id: str,
    label: str,
    quality_factor: float,
    param_configs: dict[str, Any],
    rng: np.random.Generator,
    temperature_profile: str = "125C",
) -> list[dict[str, Any]]:
    rows = []
    lot_baselines = {}
    for param in PARAMETERS:
        cfg = param_configs[param]
        lot_baselines[param] = cfg["lot_baseline_mean"] * quality_factor + rng.normal(
            0, cfg["lot_baseline_std"] * 0.3
        )

    for param in PARAMETERS:
        cfg = param_configs[param]
        spec_min = cfg["spec_min"]
        spec_max = cfg["spec_max"]
        lot_median = lot_baselines[param]
        noise = cfg["lot_baseline_std"] * 0.15

        if label == "healthy":
            values = _trajectory_healthy(lot_median, noise, rng)
        elif label == "static_fail":
            values = _trajectory_static_fail(lot_median, spec_min, spec_max, noise, rng)
        elif label == "latent_defect":
            if param == "leakage_current":
                values = _trajectory_latent_defect(lot_median, spec_max, noise, rng)
            else:
                values = _trajectory_latent_defect(lot_median, spec_max, noise * 0.5, rng)
        elif label == "gradual_drift":
            values = _trajectory_gradual_drift(lot_median, spec_max, noise, rng)
        elif label == "sudden_drift":
            values = _trajectory_sudden_drift(lot_median, spec_max, noise, rng)
        elif label == "noisy_healthy":
            values = _trajectory_noisy_healthy(lot_median, spec_max, noise, rng)
        else:
            values = _trajectory_healthy(lot_median, noise, rng)

        rows.append(
            {
                "component_id": component_id,
                "lot_id": lot_id,
                "parameter": param,
                "value_0h": round(values[0], 6),
                "value_24h": round(values[1], 6),
                "value_96h": round(values[2], 6),
                "value_168h": round(values[3], 6),
                "spec_min": spec_min,
                "spec_max": spec_max,
                "temperature_profile": temperature_profile,
                "label": label,
            }
        )
    return rows


def generate_dataset(config: dict[str, Any], seed: int | None = None) -> pd.DataFrame:
    seed = seed if seed is not None else config.get("random_seed", 42)
    rng = np.random.default_rng(seed)
    ds_cfg = config["dataset"]
    param_configs = config["parameters"]
    label_dist = config["label_distribution"]

    num_lots = ds_cfg["num_lots"]
    comp_min = ds_cfg["components_per_lot_min"]
    comp_max = ds_cfg["components_per_lot_max"]

    all_rows: list[dict[str, Any]] = []
    comp_counter = 0

    for lot_idx in range(num_lots):
        lot_id = f"LOT-{lot_idx + 1:03d}"
        quality_factor = rng.uniform(0.85, 1.15)
        n_components = rng.integers(comp_min, comp_max + 1)

        for _ in range(n_components):
            comp_counter += 1
            component_id = f"COMP-{comp_counter:05d}"
            label = _pick_label(rng, label_dist)
            rows = generate_component_rows(
                component_id, lot_id, label, quality_factor, param_configs, rng
            )
            all_rows.extend(rows)

    df = pd.DataFrame(all_rows)

    # Inject missing measurements
    miss_frac = ds_cfg.get("missing_measurement_fraction", 0.03)
    n_miss = int(len(df) * miss_frac)
    if n_miss > 0:
        miss_idx = rng.choice(len(df), size=n_miss, replace=False)
        miss_cols = rng.choice(["value_24h", "value_96h", "value_168h"], size=n_miss)
        for i, col in zip(miss_idx, miss_cols):
            df.at[i, col] = np.nan

    # Inject duplicates
    dup_frac = ds_cfg.get("duplicate_fraction", 0.005)
    n_dup = max(1, int(len(df) * dup_frac))
    dup_samples = df.sample(n=min(n_dup, len(df)), random_state=seed)
    df = pd.concat([df, dup_samples], ignore_index=True)

    # Inject invalid rows
    inv_frac = ds_cfg.get("invalid_fraction", 0.002)
    n_inv = max(1, int(len(df) * inv_frac))
    for i in range(n_inv):
        inv_row = df.iloc[rng.integers(0, len(df))].copy()
        inv_row["component_id"] = f"INVALID-{i}"
        if inv_row["parameter"] in ("iddq", "leakage_current"):
            inv_row["value_0h"] = -abs(inv_row["value_0h"])
        else:
            inv_row["value_0h"] = -1.0
        df = pd.concat([df, inv_row.to_frame().T], ignore_index=True)

    logger.info("Generated %d rows, %d unique components", len(df), df["component_id"].nunique())
    return df


def generate_demo_components(config: dict[str, Any]) -> pd.DataFrame:
    """Generate fixed demo set C001-C006 for judge-facing demo."""
    demo_cfg = config["demo"]
    seed = demo_cfg["seed"]
    rng = np.random.default_rng(seed)
    param_configs = config["parameters"]
    lot_id = "DEMO-LOT"

    all_rows: list[dict[str, Any]] = []
    for comp in demo_cfg["components"]:
        cid = comp["id"]
        label = comp["label"]
        quality = 1.0 if cid != "C006" else 1.3

        if cid == "C003":
            # Headline latent defect on leakage_current
            for param in PARAMETERS:
                cfg = param_configs[param]
                if param == "leakage_current":
                    lot_median = 10.0
                    values = [10.5, 18.2, 32.0, 45.1]
                    all_rows.append(
                        {
                            "component_id": cid,
                            "lot_id": lot_id,
                            "parameter": param,
                            "value_0h": values[0],
                            "value_24h": values[1],
                            "value_96h": values[2],
                            "value_168h": values[3],
                            "spec_min": cfg["spec_min"],
                            "spec_max": cfg["spec_max"],
                            "temperature_profile": "125C",
                            "label": "latent_defect",
                        }
                    )
                else:
                    rows = generate_component_rows(
                        cid, lot_id, "latent_defect", quality, param_configs, rng
                    )
                    row = [r for r in rows if r["parameter"] == param][0]
                    all_rows.append(row)
        elif cid == "C002":
            rows = generate_component_rows(
                cid, lot_id, "static_fail", quality, param_configs, rng
            )
            for row in rows:
                if row["parameter"] == "leakage_current":
                    row["value_96h"] = row["spec_max"] * 1.2
                    row["value_168h"] = row["spec_max"] * 1.25
                all_rows.append(row)
        elif cid == "C006":
            rows = generate_component_rows(
                cid, lot_id, "noisy_healthy", 1.8, param_configs, rng
            )
            all_rows.extend(rows)
        else:
            rows = generate_component_rows(cid, lot_id, label, quality, param_configs, rng)
            all_rows.extend(rows)

    return pd.DataFrame(all_rows)
