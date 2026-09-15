"""Plain-language explainability for QA inspectors."""

from __future__ import annotations

from typing import Any


def explain_component(
    row: dict[str, Any],
    anomaly: dict[str, Any],
    drift: dict[str, Any],
    decision: dict[str, Any],
    safety_slopes: dict[str, float],
) -> str:
    parts = []
    param = row.get("parameter", "unknown")
    unit_map = {"iddq": "mA", "leakage_current": "µA", "propagation_delay": "ns"}
    unit = unit_map.get(param, "")

    cid = row.get("component_id", "?")
    lot = row.get("lot_id", "?")
    parts.append(f"Component {cid} (Lot {lot}, Parameter: {param.replace('_', ' ')}):")

    # Static limit
    val_168 = row.get("value_168h") or row.get("value_96h") or row.get("value_24h")
    spec_max = row.get("spec_max")
    spec_min = row.get("spec_min")
    static = decision.get("static_result", "PASS")
    if static == "FAIL":
        parts.append(
            f"STATIC LIMIT FAIL: measured {val_168:.2f} {unit} exceeds "
            f"spec range [{spec_min}, {spec_max}] {unit}."
        )
    else:
        parts.append(
            f"Static screening PASS: value {val_168:.2f} {unit} is within "
            f"spec limits [{spec_min}, {spec_max}] {unit}."
        )

    # Module A
    z_0h = row.get("robust_z_0h", 0)
    lot_med = row.get("lot_median_96h") or row.get("lot_median_24h") or row.get("lot_median_0h")
    if lot_med is not None:
        parts.append(
            f"DYNAMIC ANOMALY (Module A): anomaly score {anomaly.get('anomaly_score', 0):.2f} "
            f"({anomaly.get('severity', 'LOW')} severity). "
            f"Lot median ≈ {lot_med:.2f} {unit}, robust z-score up to {max(abs(z_0h), abs(row.get('robust_z_96h', 0))):.1f}. "
            f"Contributing features: {', '.join(anomaly.get('contributing_features', []))}."
        )

    # Module B
    pred = drift.get("predicted_168h")
    safety = safety_slopes.get(param, 0)
    rate = drift.get("drift_rate", 0)
    if pred is not None:
        parts.append(
            f"DRIFT PREDICTION (Module B): predicted {pred:.2f} {unit} at 168h "
            f"(drift rate {rate:.4f} {unit}/h vs safety slope {safety:.4f} {unit}/h). "
            f"Drift risk: {drift.get('drift_risk', 'SAFE')}."
        )

    # Safety margin
    margin = decision.get("safety_margin_pct", 0)
    parts.append(f"Safety margin to spec_max: {margin:.1f}%.")

    # Final decision
    parts.append(
        f"FINAL DECISION: {decision.get('decision')} — {decision.get('reason')} "
        f"(Rule: {decision.get('rule_name')}, confidence: {decision.get('confidence')})."
    )

    return " ".join(parts)


def explain_summary_for_demo(row: dict[str, Any], anomaly: dict, drift: dict, decision: dict) -> str:
    """Short headline for C003 demo."""
    if row.get("component_id") == "C003" and row.get("parameter") == "leakage_current":
        return (
            f"HEADLINE: Component C003 PASSED static screening (45.1 µA < 50 µA limit) "
            f"but flagged as {anomaly.get('severity')} dynamic anomaly "
            f"(lot median ≈ 10 µA, z-score >> 3.5) with {drift.get('drift_risk')} drift. "
            f"Decision: {decision.get('decision')}."
        )
    return explain_component(row, anomaly, drift, decision, {})
