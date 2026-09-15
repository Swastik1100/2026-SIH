"""Tests for data validation and cleaning modules."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.preprocessing.validation import validate_schema, detect_invalid_rows, ValidationReport
from app.preprocessing.cleaning import resolve_duplicates, impute_missing, clean_dataset


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_df(**kwargs) -> pd.DataFrame:
    """Create a minimal valid dataframe with optional overrides."""
    defaults = {
        "component_id": ["C001", "C001", "C002"],
        "lot_id": ["L1", "L1", "L1"],
        "parameter": ["iddq", "leakage_current", "iddq"],
        "value_0h": [1.0, 5.0, 1.2],
        "value_24h": [1.1, 5.5, 1.3],
        "value_96h": [1.2, 6.0, 1.4],
        "value_168h": [1.3, 6.5, 1.5],
        "spec_min": [0.1, 0.0, 0.1],
        "spec_max": [5.0, 50.0, 5.0],
        "label": ["healthy", "healthy", "healthy"],
        "temperature_profile": ["125C", "125C", "125C"],
    }
    defaults.update(kwargs)
    return pd.DataFrame(defaults)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidateSchema:
    def test_valid_df_returns_report(self):
        df = make_df()
        report = validate_schema(df)
        assert isinstance(report, ValidationReport)
        assert report.total_rows == 3

    def test_missing_required_column_raises(self):
        df = make_df()
        df = df.drop(columns=["value_0h"])
        with pytest.raises(ValueError, match="Missing required columns"):
            validate_schema(df)

    def test_missing_values_reported(self):
        df = make_df()
        df.loc[0, "value_24h"] = np.nan
        df.loc[1, "value_96h"] = np.nan
        report = validate_schema(df)
        assert "value_24h" in report.missing_counts
        assert "value_96h" in report.missing_counts
        assert report.missing_counts["value_24h"] == 1

    def test_duplicate_detection(self):
        df = make_df(
            component_id=["C001", "C001", "C002"],
            parameter=["iddq", "iddq", "iddq"],  # C001/iddq duplicated
        )
        report = validate_schema(df)
        assert report.duplicate_groups >= 1


class TestDetectInvalidRows:
    def test_negative_current_flagged(self):
        df = make_df(
            component_id=["BAD"],
            lot_id=["L1"],
            parameter=["iddq"],
            value_0h=[-1.0],   # invalid: negative current
            value_24h=[1.0],
            value_96h=[1.0],
            value_168h=[1.0],
            spec_min=[0.1],
            spec_max=[5.0],
            label=["healthy"],
            temperature_profile=["125C"],
        )
        invalid = detect_invalid_rows(df)
        assert len(invalid) == 1
        assert "rejection_reason" in invalid.columns
        assert "negative" in invalid.iloc[0]["rejection_reason"].lower()

    def test_nonpositive_delay_flagged(self):
        df = make_df(
            component_id=["BAD"],
            lot_id=["L1"],
            parameter=["propagation_delay"],
            value_0h=[-0.5],
            value_24h=[1.0],
            value_96h=[1.0],
            value_168h=[1.0],
            spec_min=[1.0],
            spec_max=[15.0],
            label=["healthy"],
            temperature_profile=["125C"],
        )
        invalid = detect_invalid_rows(df)
        assert len(invalid) == 1

    def test_valid_rows_not_flagged(self):
        df = make_df()
        invalid = detect_invalid_rows(df)
        assert len(invalid) == 0

    def test_invalid_rows_not_silently_dropped(self):
        """Invalid rows must appear in rejected_records, not be silently removed."""
        df = make_df(
            component_id=["GOOD", "BAD"],
            lot_id=["L1", "L1"],
            parameter=["iddq", "leakage_current"],
            value_0h=[1.0, -5.0],
            value_24h=[1.1, 1.0],
            value_96h=[1.2, 1.0],
            value_168h=[1.3, 1.0],
            spec_min=[0.1, 0.0],
            spec_max=[5.0, 50.0],
            label=["healthy", "healthy"],
            temperature_profile=["125C", "125C"],
        )
        invalid = detect_invalid_rows(df)
        # The bad row must be captured, not silently discarded
        assert len(invalid) == 1
        assert "rejection_reason" in invalid.columns


# ---------------------------------------------------------------------------
# Cleaning tests
# ---------------------------------------------------------------------------

class TestResolveDuplicates:
    def test_keeps_most_complete_row(self):
        df = pd.DataFrame({
            "component_id": ["C001", "C001"],
            "lot_id": ["L1", "L1"],
            "parameter": ["iddq", "iddq"],
            "value_0h": [1.0, 1.0],
            "value_24h": [np.nan, 1.1],  # second row is more complete
            "value_96h": [np.nan, 1.2],
            "value_168h": [np.nan, 1.3],
        })
        cleaned = resolve_duplicates(df)
        assert len(cleaned) == 1
        assert cleaned.iloc[0]["value_24h"] == 1.1

    def test_no_duplicates_unchanged(self):
        df = make_df()
        # C001 has iddq and leakage_current — different params, not duplicates
        cleaned = resolve_duplicates(df)
        assert len(cleaned) == len(df)


class TestImputeMissing:
    def test_forward_fill_applied(self):
        df = pd.DataFrame({
            "component_id": ["C001"],
            "lot_id": ["L1"],
            "parameter": ["iddq"],
            "value_0h": [1.0],
            "value_24h": [np.nan],
            "value_96h": [np.nan],
            "value_168h": [np.nan],
        })
        cleaned, log = impute_missing(df)
        # Should forward-fill with 1.0
        assert cleaned.iloc[0]["value_24h"] == 1.0
        assert len(log) == 1

    def test_imputation_logged(self):
        df = pd.DataFrame({
            "component_id": ["C001"],
            "lot_id": ["L1"],
            "parameter": ["iddq"],
            "value_0h": [1.0],
            "value_24h": [np.nan],
            "value_96h": [1.5],
            "value_168h": [1.6],
        })
        cleaned, log = impute_missing(df)
        assert len(log) >= 1
        assert cleaned.iloc[0]["was_imputed"] is True


class TestCleanDataset:
    def test_invalid_rows_removed(self):
        df = make_df(
            component_id=["GOOD", "BAD"],
            lot_id=["L1", "L1"],
            parameter=["iddq", "leakage_current"],
            value_0h=[1.0, -5.0],
            value_24h=[1.1, 1.0],
            value_96h=[1.2, 1.0],
            value_168h=[1.3, 1.0],
            spec_min=[0.1, 0.0],
            spec_max=[5.0, 50.0],
            label=["healthy", "healthy"],
            temperature_profile=["125C", "125C"],
        )
        invalid = detect_invalid_rows(df)
        cleaned = clean_dataset(df, invalid)
        assert "BAD" not in cleaned["component_id"].values
        assert "GOOD" in cleaned["component_id"].values
