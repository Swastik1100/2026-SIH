"""Data validation with explicit logging."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = [
    "component_id",
    "lot_id",
    "parameter",
    "value_0h",
    "value_24h",
    "value_96h",
    "value_168h",
    "spec_min",
    "spec_max",
]


@dataclass
class ValidationReport:
    total_rows: int = 0
    missing_counts: dict[str, int] = field(default_factory=dict)
    duplicate_groups: int = 0
    invalid_rows: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_rows": self.total_rows,
            "missing_counts": self.missing_counts,
            "duplicate_groups": self.duplicate_groups,
            "invalid_rows": self.invalid_rows,
            "warnings": self.warnings,
        }


def validate_schema(df: pd.DataFrame) -> ValidationReport:
    report = ValidationReport(total_rows=len(df))
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    for col in ["value_0h", "value_24h", "value_96h", "value_168h"]:
        n_miss = int(df[col].isna().sum())
        if n_miss:
            report.missing_counts[col] = n_miss
            msg = f"Column {col}: {n_miss} missing values"
            report.warnings.append(msg)
            logger.warning(msg)

    dup_mask = df.duplicated(subset=["component_id", "parameter"], keep=False)
    report.duplicate_groups = int(df[dup_mask]["component_id"].nunique())
    if report.duplicate_groups:
        msg = f"Found {report.duplicate_groups} component/parameter duplicate groups"
        report.warnings.append(msg)
        logger.warning(msg)

    return report


def detect_invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return invalid rows with reason column."""
    reasons = []
    invalid_indices = []

    for idx, row in df.iterrows():
        reason_parts = []
        param = row["parameter"]
        for col in ["value_0h", "value_24h", "value_96h", "value_168h"]:
            val = row[col]
            if pd.isna(val):
                continue
            if param in ("iddq", "leakage_current") and val < 0:
                reason_parts.append(f"negative current in {col}")
            if param == "propagation_delay" and val <= 0:
                reason_parts.append(f"non-positive delay in {col}")

        if reason_parts:
            invalid_indices.append(idx)
            reasons.append("; ".join(reason_parts))

    if not invalid_indices:
        return pd.DataFrame(columns=list(df.columns) + ["rejection_reason"])

    invalid_df = df.loc[invalid_indices].copy()
    invalid_df["rejection_reason"] = reasons
    logger.info("Quarantined %d invalid rows", len(invalid_df))
    return invalid_df
