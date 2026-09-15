"""Pydantic v2 schemas for API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MeasurementInput(BaseModel):
    component_id: str
    lot_id: str
    parameter: str
    value_0h: float
    value_24h: float | None = None
    value_96h: float | None = None
    value_168h: float | None = None
    spec_min: float
    spec_max: float
    temperature_profile: str = "125C"


class PredictRequest(BaseModel):
    measurements: list[MeasurementInput]


class AnomalyResult(BaseModel):
    robust_z_score: float
    isolation_forest_score: float
    anomaly_score: float
    anomaly_label: bool
    severity: str
    contributing_features: list[str]


class DriftResult(BaseModel):
    predicted_168h: float | None
    predicted_drift: float | None
    drift_rate: float | None
    drift_risk: str
    drift_ratio: float | None = None


class DecisionResult(BaseModel):
    decision: str
    reason: str
    rule_name: str
    static_result: str
    safety_margin_pct: float
    confidence: str


class ComponentPrediction(BaseModel):
    component_id: str
    lot_id: str
    parameter: str
    measurements: dict[str, float | None]
    anomaly: AnomalyResult
    drift: DriftResult
    decision: DecisionResult
    explanation: str


class PredictResponse(BaseModel):
    results: list[ComponentPrediction]


class ScreenRequest(BaseModel):
    measurements: list[MeasurementInput]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"


class MetricsResponse(BaseModel):
    module_a: dict[str, Any] = Field(default_factory=dict)
    module_b: dict[str, Any] = Field(default_factory=dict)
    screening: dict[str, Any] = Field(default_factory=dict)
    baseline_comparison: dict[str, Any] = Field(default_factory=dict)


class LotSummary(BaseModel):
    lot_id: str
    component_count: int
    parameters: list[str]
    statistics: dict[str, Any]
    anomalous_components: list[str]


class ComponentDetail(BaseModel):
    component_id: str
    lot_id: str
    records: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
