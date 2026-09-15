"""Data cleaning with traceable imputation."""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def resolve_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Keep row with fewest NaNs per component_id + parameter."""
    if df.empty:
        return df

    def completeness(row: pd.Series) -> int:
        cols = ["value_0h", "value_24h", "value_96h", "value_168h"]
        return sum(1 for c in cols if pd.notna(row[c]))

    df = df.copy()
    df["_completeness"] = df.apply(completeness, axis=1)
    before = len(df)
    df = df.sort_values("_completeness", ascending=False)
    df = df.drop_duplicates(subset=["component_id", "parameter"], keep="first")
    df = df.drop(columns=["_completeness"])
    removed = before - len(df)
    if removed:
        logger.info("Removed %d duplicate rows (kept most complete)", removed)
    return df.reset_index(drop=True)


def impute_missing(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Forward-fill missing checkpoint values per component/parameter.
    Returns (cleaned_df, imputation_log).
    """
    df = df.copy()
    checkpoint_cols = ["value_0h", "value_24h", "value_96h", "value_168h"]
    log_rows = []

    for idx, row in df.iterrows():
        values = [row[c] for c in checkpoint_cols]
        imputed_cols = []
        last_known = None
        for i, col in enumerate(checkpoint_cols):
            if pd.notna(row[col]):
                last_known = row[col]
            elif last_known is not None:
                df.at[idx, col] = last_known
                imputed_cols.append(col)
        if imputed_cols:
            log_rows.append(
                {
                    "component_id": row["component_id"],
                    "parameter": row["parameter"],
                    "imputed_columns": ",".join(imputed_cols),
                }
            )

    imputation_log = pd.DataFrame(log_rows)
    if len(imputation_log):
        logger.info("Imputed missing values for %d rows", len(imputation_log))
    df["was_imputed"] = df.apply(
        lambda r: any(
            r["component_id"] == log["component_id"] and r["parameter"] == log["parameter"]
            for _, log in imputation_log.iterrows()
        )
        if len(imputation_log)
        else False,
        axis=1,
    )
    return df, imputation_log


def clean_dataset(df: pd.DataFrame, invalid_df: pd.DataFrame) -> pd.DataFrame:
    """Remove invalid rows and clean duplicates."""
    if not invalid_df.empty:
        invalid_ids = set(invalid_df.index)
        df = df.drop(index=invalid_ids, errors="ignore").reset_index(drop=True)
    df = resolve_duplicates(df)
    df, _ = impute_missing(df)
    return df
