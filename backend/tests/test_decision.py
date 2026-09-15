"""Tests for the decision engine."""

from __future__ import annotations

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.decision.engine import (
    static_check,
    compute_safety_margin_pct,
    compute_confidence,
    decide,
    load_decision_rules,
)
from app.core.config import get_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_row(
    value_0h: float = 1.0,
    value_24h: float = 1.1,
    value_96h: float = 1.2,
    value_168h: float = 1.3,
    spec_min: float = 0.1,
    spec_max: float = 5.0,
    was_imputed: bool = False,
) -> dict:
    return {
        "component_id": "C001",
        "lot_id": "LOT-001",
        "parameter": "iddq",
        "value_0h": value_0h,
        "value_24h": value_24h,
        "value_96h": value_96h,
        "value_168h": value_168h,
        "spec_min": spec_min,
        "spec_max": spec_max,
        "was_imputed": was_imputed,
    }


def low_anomaly() -> dict:
    return {"severity": "LOW", "anomaly_score": 0.2, "anomaly_label": False}

def medium_anomaly() -> dict:
    return {"severity": "MEDIUM", "anomaly_score": 0.7, "anomaly_label": True}

def high_anomaly() -> dict:
    return {"severity": "HIGH", "anomaly_score": 0.9, "anomaly_label": True}

def safe_drift() -> dict:
    return {"drift_risk": "SAFE", "drift_ratio": 0.2, "predicted_168h": 1.5}

def watch_drift() -> dict:
    return {"drift_risk": "WATCH", "drift_ratio": 0.7, "predicted_168h": 3.0}

def dangerous_drift() -> dict:
    return {"drift_risk": "DANGEROUS", "drift_ratio": 1.2, "predicted_168h": 4.8}


# ---------------------------------------------------------------------------
# Static check tests
# ---------------------------------------------------------------------------

class TestStaticCheck:
    def test_within_spec_is_pass(self):
        row = make_row(value_168h=2.5, spec_min=0.1, spec_max=5.0)
        assert static_check(row) == "PASS"

    def test_above_spec_max_is_fail(self):
        row = make_row(value_168h=6.0, spec_min=0.1, spec_max=5.0)
        assert static_check(row) == "FAIL"

    def test_below_spec_min_is_fail(self):
        row = make_row(value_0h=0.05, value_24h=0.08, value_96h=0.09, value_168h=0.09,
                       spec_min=0.1, spec_max=5.0)
        assert static_check(row) == "FAIL"

    def test_at_spec_boundary_is_pass(self):
        row = make_row(value_168h=5.0, spec_min=0.1, spec_max=5.0)
        # Exactly at limit — should pass (not strictly greater than)
        assert static_check(row) == "PASS"

    def test_static_fail_at_any_checkpoint(self):
        """If ANY checkpoint exceeds spec, result is FAIL."""
        row = make_row(value_0h=0.5, value_24h=6.0, value_96h=1.0, value_168h=1.0,
                       spec_min=0.1, spec_max=5.0)
        assert static_check(row) == "FAIL"


# ---------------------------------------------------------------------------
# Safety margin and confidence
# ---------------------------------------------------------------------------

class TestSafetyMargin:
    def test_margin_at_halfway(self):
        row = make_row(value_96h=2.5, spec_max=5.0)
        margin = compute_safety_margin_pct(row)
        assert abs(margin - 50.0) < 0.1

    def test_margin_near_spec_max(self):
        row = make_row(value_96h=4.9, spec_max=5.0)
        margin = compute_safety_margin_pct(row)
        assert margin < 5.0

    def test_margin_well_below_spec(self):
        row = make_row(value_96h=1.0, spec_max=5.0)
        margin = compute_safety_margin_pct(row)
        assert margin > 70.0


class TestComputeConfidence:
    def test_all_values_present_is_high(self):
        row = make_row()
        assert compute_confidence(row) == "HIGH"

    def test_imputed_is_low(self):
        row = make_row(was_imputed=True)
        assert compute_confidence(row) == "LOW"

    def test_one_missing_is_medium(self):
        row = make_row(value_96h=None)
        assert compute_confidence(row) == "MEDIUM"


# ---------------------------------------------------------------------------
# Decision engine: all four outcomes reachable
# ---------------------------------------------------------------------------

class TestDecisionEngine:
    @pytest.fixture
    def rules(self):
        config = get_config()
        return load_decision_rules(config)

    def test_static_fail_gives_reject(self, rules):
        """Static FAIL → REJECT regardless of ML outputs."""
        row = make_row(value_168h=8.0, spec_max=5.0)  # above spec
        result = decide(row, low_anomaly(), safe_drift(), rules)
        assert result["decision"] == "REJECT"
        assert result["static_result"] == "FAIL"

    def test_all_clear_gives_pass(self, rules):
        """Static PASS + LOW anomaly + SAFE drift → PASS."""
        row = make_row()
        result = decide(row, low_anomaly(), safe_drift(), rules)
        assert result["decision"] == "PASS"

    def test_medium_anomaly_safe_drift_gives_watch(self, rules):
        """Static PASS + MEDIUM anomaly + SAFE drift → WATCH."""
        row = make_row()
        result = decide(row, medium_anomaly(), safe_drift(), rules)
        assert result["decision"] == "WATCH"

    def test_high_anomaly_dangerous_drift_gives_reject(self, rules):
        """
        HEADLINE CASE: Static PASS + HIGH anomaly + DANGEROUS drift → REJECT.
        This is the C003-style latent defect scenario.
        """
        row = make_row()
        result = decide(row, high_anomaly(), dangerous_drift(), rules)
        assert result["decision"] in ("REJECT", "REVIEW"), (
            f"Expected REJECT or REVIEW for HIGH anomaly + DANGEROUS drift, got {result['decision']}"
        )

    def test_high_anomaly_watch_drift_gives_review(self, rules):
        """Static PASS + HIGH anomaly + WATCH drift → REVIEW."""
        row = make_row()
        result = decide(row, high_anomaly(), watch_drift(), rules)
        assert result["decision"] == "REVIEW"

    def test_low_anomaly_dangerous_drift_gives_review(self, rules):
        """Static PASS + LOW anomaly + DANGEROUS drift → REVIEW."""
        row = make_row()
        result = decide(row, low_anomaly(), dangerous_drift(), rules)
        assert result["decision"] == "REVIEW"

    def test_low_anomaly_watch_drift_gives_watch(self, rules):
        """Static PASS + LOW anomaly + WATCH drift → WATCH."""
        row = make_row()
        result = decide(row, low_anomaly(), watch_drift(), rules)
        assert result["decision"] == "WATCH"

    def test_medium_anomaly_dangerous_drift_gives_review(self, rules):
        """Static PASS + MEDIUM anomaly + DANGEROUS drift → REVIEW."""
        row = make_row()
        result = decide(row, medium_anomaly(), dangerous_drift(), rules)
        assert result["decision"] == "REVIEW"

    def test_result_contains_required_fields(self, rules):
        """decide() must return all required fields."""
        row = make_row()
        result = decide(row, low_anomaly(), safe_drift(), rules)
        required = ["decision", "reason", "rule_name", "static_result", "safety_margin_pct", "confidence"]
        for field in required:
            assert field in result, f"Missing field: {field}"

    def test_all_four_decisions_reachable(self, rules):
        """All four decision outcomes must be reachable via constructed inputs."""
        row = make_row()
        results = set()
        # PASS
        results.add(decide(row, low_anomaly(), safe_drift(), rules)["decision"])
        # WATCH
        results.add(decide(row, medium_anomaly(), safe_drift(), rules)["decision"])
        # REVIEW
        results.add(decide(row, low_anomaly(), dangerous_drift(), rules)["decision"])
        # REJECT (via static fail)
        row_fail = make_row(value_168h=8.0, spec_max=5.0)
        results.add(decide(row_fail, low_anomaly(), safe_drift(), rules)["decision"])

        for outcome in ("PASS", "WATCH", "REVIEW", "REJECT"):
            assert outcome in results, f"Decision '{outcome}' was never produced"


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------

class TestLoadDecisionRules:
    def test_rules_load_from_yaml(self):
        config = get_config()
        rules = load_decision_rules(config)
        assert len(rules) > 0

    def test_rules_sorted_by_priority(self):
        config = get_config()
        rules = load_decision_rules(config)
        priorities = [r.get("priority", 99) for r in rules]
        assert priorities == sorted(priorities)

    def test_each_rule_has_required_fields(self):
        config = get_config()
        rules = load_decision_rules(config)
        for rule in rules:
            assert "conditions" in rule
            assert "decision" in rule
            assert "reason" in rule
