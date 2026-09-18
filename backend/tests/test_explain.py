"""Tests for the explainability module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.explainability.explain import explain_component, explain_summary_for_demo


@pytest.fixture
def healthy_row():
    return {
        "component_id": "C001",
        "lot_id": "LOT-001",
        "parameter": "leakage_current",
        "value_0h": 10.0,
        "value_24h": 10.5,
        "value_96h": 11.0,
        "value_168h": 11.3,
        "spec_min": 0.0,
        "spec_max": 50.0,
        "robust_z_0h": 0.3,
        "robust_z_96h": 0.5,
        "lot_median_96h": 10.2,
    }


@pytest.fixture
def latent_defect_row():
    return {
        "component_id": "C003",
        "lot_id": "DEMO-LOT",
        "parameter": "leakage_current",
        "value_0h": 10.5,
        "value_24h": 18.2,
        "value_96h": 32.0,
        "value_168h": 45.1,
        "spec_min": 0.0,
        "spec_max": 50.0,
        "robust_z_0h": 0.3,
        "robust_z_96h": 8.2,
        "lot_median_96h": 10.2,
    }


@pytest.fixture
def anomaly_high():
    return {
        "anomaly_score": 0.87,
        "severity": "HIGH",
        "contributing_features": ["robust_z_96h: z=8.20", "robust_z_24h: z=5.10"],
    }


@pytest.fixture
def anomaly_low():
    return {
        "anomaly_score": 0.12,
        "severity": "LOW",
        "contributing_features": ["robust_z_0h: z=0.30"],
    }


@pytest.fixture
def drift_dangerous():
    return {
        "predicted_168h": 45.5,
        "drift_rate": 0.242,
        "drift_risk": "DANGEROUS",
        "drift_ratio": 1.35,
    }


@pytest.fixture
def drift_safe():
    return {
        "predicted_168h": 11.5,
        "drift_rate": 0.005,
        "drift_risk": "SAFE",
        "drift_ratio": 0.12,
    }


@pytest.fixture
def decision_reject():
    return {
        "decision": "REJECT",
        "reason": "High anomaly + dangerous drift.",
        "rule_name": "High anomaly + dangerous drift → REJECT",
        "static_result": "PASS",
        "safety_margin_pct": 9.8,
        "confidence": "HIGH",
    }


@pytest.fixture
def decision_pass():
    return {
        "decision": "PASS",
        "reason": "All clear.",
        "rule_name": "All clear → PASS",
        "static_result": "PASS",
        "safety_margin_pct": 77.4,
        "confidence": "HIGH",
    }


class TestExplainComponent:
    def test_returns_string(self, healthy_row, anomaly_low, drift_safe, decision_pass):
        result = explain_component(healthy_row, anomaly_low, drift_safe, decision_pass, {})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_component_id(self, healthy_row, anomaly_low, drift_safe, decision_pass):
        result = explain_component(healthy_row, anomaly_low, drift_safe, decision_pass, {})
        assert "C001" in result

    def test_contains_decision(self, healthy_row, anomaly_low, drift_safe, decision_pass):
        result = explain_component(healthy_row, anomaly_low, drift_safe, decision_pass, {})
        assert "PASS" in result

    def test_latent_defect_mentions_high_severity(self, latent_defect_row, anomaly_high, drift_dangerous, decision_reject):
        result = explain_component(latent_defect_row, anomaly_high, drift_dangerous, decision_reject,
                                   {"leakage_current": 0.18})
        assert "HIGH" in result
        assert "DANGEROUS" in result
        assert "REJECT" in result

    def test_handles_none_value_168h_gracefully(self, anomaly_low, drift_safe, decision_pass):
        """Must not crash when value_168h, value_96h, value_24h are all None."""
        row = {
            "component_id": "CMISSING",
            "lot_id": "LOT-X",
            "parameter": "iddq",
            "value_0h": 1.5,
            "value_24h": None,
            "value_96h": None,
            "value_168h": None,
            "spec_min": 0.1,
            "spec_max": 5.0,
            "robust_z_0h": 0.1,
            "robust_z_96h": 0.0,
            "lot_median_96h": None,
        }
        result = explain_component(row, anomaly_low, drift_safe, decision_pass, {})
        assert isinstance(result, str)  # Must not raise

    def test_handles_missing_lot_median(self, anomaly_low, drift_safe, decision_pass):
        """Should not crash when lot_median_96h is missing."""
        row = {
            "component_id": "C099",
            "lot_id": "LOT-NEW",
            "parameter": "propagation_delay",
            "value_0h": 5.0,
            "value_24h": 5.1,
            "value_96h": 5.2,
            "value_168h": 5.3,
            "spec_min": 1.0,
            "spec_max": 15.0,
            "robust_z_0h": 0.05,
            "robust_z_96h": 0.08,
            # No lot_median keys
        }
        result = explain_component(row, anomaly_low, drift_safe, decision_pass, {})
        assert isinstance(result, str)

    def test_fail_static_mentions_spec_limits(self, latent_defect_row, anomaly_low, drift_safe):
        decision_fail = {
            "decision": "REJECT",
            "reason": "Exceeds spec limits.",
            "rule_name": "Static fail → REJECT",
            "static_result": "FAIL",
            "safety_margin_pct": 0.0,
            "confidence": "HIGH",
        }
        result = explain_component(latent_defect_row, anomaly_low, drift_safe, decision_fail, {})
        assert "STATIC LIMIT FAIL" in result


class TestExplainSummaryForDemo:
    def test_c003_returns_headline(self, latent_defect_row, anomaly_high, drift_dangerous, decision_reject):
        result = explain_summary_for_demo(latent_defect_row, anomaly_high, drift_dangerous, decision_reject)
        assert "HEADLINE" in result
        assert "C003" in result
        assert "HIGH" in result
        assert "REJECT" in result

    def test_non_c003_returns_standard_explain(self, healthy_row, anomaly_low, drift_safe, decision_pass):
        result = explain_summary_for_demo(healthy_row, anomaly_low, drift_safe, decision_pass)
        # Should fall through to explain_component (no HEADLINE prefix)
        assert "HEADLINE" not in result
        assert "C001" in result

    def test_c003_values_derived_from_row(self, anomaly_high, drift_dangerous, decision_reject):
        """Explanation should use actual row values, not hardcoded ones."""
        custom_row = {
            "component_id": "C003",
            "lot_id": "DEMO-LOT",
            "parameter": "leakage_current",
            "value_0h": 10.0,
            "value_24h": 15.0,
            "value_96h": 25.0,
            "value_168h": 42.0,   # Different from hardcoded 45.1
            "spec_min": 0.0,
            "spec_max": 50.0,
            "robust_z_0h": 0.3,
            "robust_z_96h": 6.1,
            "lot_median_96h": 11.0,
        }
        result = explain_summary_for_demo(custom_row, anomaly_high, drift_dangerous, decision_reject)
        assert "42.0" in result  # Uses actual value
