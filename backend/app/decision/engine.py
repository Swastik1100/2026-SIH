"""Transparent rule-based decision engine."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_decision_rules(config: dict[str, Any]) -> list[dict[str, Any]]:
    rules_file = config.get("decision_rules_file", "configs/decision_rules.yaml")
    backend_root = Path(__file__).resolve().parents[2]
    path = backend_root / rules_file
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return sorted(data["rules"], key=lambda r: r.get("priority", 99))


def static_check(row: dict[str, Any]) -> str:
    """Check absolute spec limits at latest available checkpoint."""
    for col in ["value_168h", "value_96h", "value_24h", "value_0h"]:
        val = row.get(col)
        if val is None or (isinstance(val, float) and val != val):
            continue
        if val < row.get("spec_min", float("-inf")) or val > row.get("spec_max", float("inf")):
            return "FAIL"
    return "PASS"


def compute_safety_margin_pct(row: dict[str, Any]) -> float:
    # Use explicit None checks — 0.0 is a valid measurement value and must not be skipped
    val = (
        row.get("value_96h") if row.get("value_96h") is not None
        else row.get("value_24h") if row.get("value_24h") is not None
        else row.get("value_0h", 0)
    )
    spec_max = row.get("spec_max", 1)
    if spec_max <= 0:
        return 100.0
    return max(0.0, (spec_max - val) / spec_max * 100)


def compute_confidence(row: dict[str, Any]) -> str:
    if row.get("was_imputed"):
        return "LOW"
    missing = sum(
        1
        for c in ["value_0h", "value_24h", "value_96h"]
        if row.get(c) is None or (isinstance(row.get(c), float) and row.get(c) != row.get(c))
    )
    if missing == 0:
        return "HIGH"
    if missing == 1:
        return "MEDIUM"
    return "LOW"


def _match_rule(rule: dict[str, Any], context: dict[str, Any]) -> bool:
    """Match rule conditions. Supports exact equality and range operators (lt, gt, lte, gte)."""
    conditions = rule.get("conditions", {})
    for key, expected in conditions.items():
        val = context.get(key)
        if isinstance(expected, dict):
            # Range condition: {lt: 5.0}, {gt: 80.0}, etc.
            if "lt" in expected and not (val is not None and val < expected["lt"]):
                return False
            if "lte" in expected and not (val is not None and val <= expected["lte"]):
                return False
            if "gt" in expected and not (val is not None and val > expected["gt"]):
                return False
            if "gte" in expected and not (val is not None and val >= expected["gte"]):
                return False
        else:
            if val != expected:
                return False
    return True


def decide(
    row: dict[str, Any],
    anomaly_result: dict[str, Any],
    drift_result: dict[str, Any],
    rules: list[dict[str, Any]],
    default_decision: str = "REVIEW",
    default_reason: str = "Mixed signals — manual QA review recommended.",
) -> dict[str, Any]:
    static_result = static_check(row)
    context = {
        "static_result": static_result,
        "anomaly_severity": anomaly_result.get("severity", "LOW"),
        "drift_risk": drift_result.get("drift_risk", "SAFE"),
        "safety_margin_pct": compute_safety_margin_pct(row),
        "confidence": compute_confidence(row),
    }

    for rule in rules:
        if _match_rule(rule, context):
            return {
                "decision": rule["decision"],
                "reason": rule["reason"],
                "rule_name": rule["name"],
                "static_result": static_result,
                **context,
            }

    return {
        "decision": default_decision,
        "reason": default_reason,
        "rule_name": "default",
        "static_result": static_result,
        **context,
    }
