"""FastAPI route handlers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.data.database import ScreeningResult, get_db, init_db
from app.preprocessing.features import compute_lot_stats, engineer_features
from app.schemas.api import (
    ComponentDetail,
    HealthResponse,
    LotSummary,
    MetricsResponse,
    PredictRequest,
    PredictResponse,
    ScreenRequest,
)
from app.services.pipeline import get_pipeline

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()


def _measurements_to_df(measurements: list) -> pd.DataFrame:
    rows = [m.model_dump() for m in measurements]
    return pd.DataFrame(rows)


@router.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    pipeline = get_pipeline()
    if not pipeline._trained:
        raise HTTPException(status_code=503, detail="Models not trained. Run pipeline first.")
    df = _measurements_to_df(request.measurements)
    lot_stats = compute_lot_stats(df)
    featured = engineer_features(df, lot_stats)
    results = [pipeline.process_row(row) for _, row in featured.iterrows()]
    return PredictResponse(results=results)


@router.post("/anomaly")
def anomaly_only(request: PredictRequest):
    pipeline = get_pipeline()
    if not pipeline._trained:
        raise HTTPException(status_code=503, detail="Models not trained. Run pipeline first.")
    df = _measurements_to_df(request.measurements)
    featured = engineer_features(df, compute_lot_stats(df))
    scores = pipeline.module_a.score_dataframe(featured)
    return scores.to_dict(orient="records")


@router.post("/drift")
def drift_only(request: PredictRequest):
    pipeline = get_pipeline()
    if not pipeline._trained:
        raise HTTPException(status_code=503, detail="Models not trained. Run pipeline first.")
    df = _measurements_to_df(request.measurements)
    featured = engineer_features(df, compute_lot_stats(df))
    preds = pipeline.module_b.predict(featured)
    featured_reset = featured.reset_index(drop=True)
    preds["parameter"] = featured_reset["parameter"]
    risks = pipeline.module_b.classify_drift_risk(preds, pipeline.safety_slopes)
    out = pd.concat([preds, risks], axis=1)
    out["parameter"] = featured_reset["parameter"]
    return out.to_dict(orient="records")


@router.post("/screen")
def screen_batch(request: ScreenRequest, db: Session = Depends(get_db)):
    pipeline = get_pipeline()
    df = _measurements_to_df(request.measurements)
    results = pipeline.screen_dataframe(df, persist=True)
    return {"count": len(results), "results": results}


@router.get("/component/{component_id}", response_model=ComponentDetail)
def get_component(component_id: str, db: Session = Depends(get_db)):
    records = db.query(ScreeningResult).filter(ScreeningResult.component_id == component_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="Component not found")
    recs = []
    decisions = []
    for r in records:
        recs.append(
            {
                "parameter": r.parameter,
                "value_0h": r.value_0h,
                "value_24h": r.value_24h,
                "value_96h": r.value_96h,
                "value_168h": r.value_168h,
                "spec_min": r.spec_min,
                "spec_max": r.spec_max,
            }
        )
        decisions.append(
            {
                "parameter": r.parameter,
                "static_result": r.static_result,
                "anomaly_score": r.anomaly_score,
                "anomaly_severity": r.anomaly_severity,
                "predicted_168h": r.predicted_168h,
                "drift_risk": r.drift_risk,
                "final_decision": r.final_decision,
                "explanation": r.explanation,
            }
        )
    return ComponentDetail(
        component_id=component_id,
        lot_id=records[0].lot_id,
        records=recs,
        decisions=decisions,
    )


@router.get("/lot/{lot_id}", response_model=LotSummary)
def get_lot(lot_id: str, db: Session = Depends(get_db)):
    records = db.query(ScreeningResult).filter(ScreeningResult.lot_id == lot_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="Lot not found")

    params = list({r.parameter for r in records})
    stats = {}
    for p in params:
        vals = [r.value_168h or r.value_96h for r in records if r.parameter == p]
        vals = [v for v in vals if v is not None]
        if vals:
            s = pd.Series(vals)
            stats[p] = {
                "mean": round(float(s.mean()), 4),
                "median": round(float(s.median()), 4),
                "std": round(float(s.std()), 4),
                "mad": round(float((s - s.median()).abs().median()), 4),
            }

    anomalous = list(
        {r.component_id for r in records if r.anomaly_severity in ("MEDIUM", "HIGH")}
    )
    return LotSummary(
        lot_id=lot_id,
        component_count=len({r.component_id for r in records}),
        parameters=params,
        statistics=stats,
        anomalous_components=anomalous,
    )


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics():
    report_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "evaluation_report.json"
    if not report_path.exists():
        return MetricsResponse()
    with open(report_path) as f:
        data = json.load(f)
    return MetricsResponse(**data)


@router.get("/screening-results")
def list_screening_results(
    page: int = 1,
    page_size: int = 100,
    decision: str | None = None,
    db: Session = Depends(get_db),
):
    from sqlalchemy import func as sqlfunc

    page_size = min(page_size, 500)  # Hard cap
    offset = (page - 1) * page_size

    query = db.query(ScreeningResult)
    if decision:
        query = query.filter(ScreeningResult.final_decision == decision.upper())

    total = query.with_entities(sqlfunc.count(ScreeningResult.id)).scalar() or 0
    records = query.order_by(ScreeningResult.id.desc()).offset(offset).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [
            {
                "component_id": r.component_id,
                "lot_id": r.lot_id,
                "parameter": r.parameter,
                "static_result": r.static_result,
                "anomaly_score": r.anomaly_score,
                "predicted_168h": r.predicted_168h,
                "drift_risk": r.drift_risk,
                "final_decision": r.final_decision,
                "explanation": r.explanation[:200] + "..." if len(r.explanation or "") > 200 else r.explanation,
                "label": r.label,
            }
            for r in records
        ],
    }


@router.get("/dashboard-stats")
def dashboard_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func as sqlfunc

    total_records = db.query(sqlfunc.count(ScreeningResult.id)).scalar() or 0
    if total_records == 0:
        return {"total": 0, "decisions": {}, "anomaly_rate": 0, "total_components": 0, "total_records": 0, "escaped_defects_prevented": 0}

    # Aggregate queries — no full table scan
    decision_rows = (
        db.query(ScreeningResult.final_decision, sqlfunc.count(ScreeningResult.id))
        .group_by(ScreeningResult.final_decision)
        .all()
    )
    decisions = {(d or "UNKNOWN"): cnt for d, cnt in decision_rows}

    total_components = db.query(sqlfunc.count(sqlfunc.distinct(ScreeningResult.component_id))).scalar() or 0

    anomalous = (
        db.query(sqlfunc.count(ScreeningResult.id))
        .filter(ScreeningResult.anomaly_severity.in_(["MEDIUM", "HIGH"]))
        .scalar()
        or 0
    )

    report_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "evaluation_report.json"
    escaped_prevented = 0
    if report_path.exists():
        with open(report_path) as f:
            data = json.load(f)
        bc = data.get("baseline_comparison", {})
        static_fn = bc.get("static_only", {}).get("false_negatives", 0)
        full_fn = bc.get("full_system", {}).get("false_negatives", 0)
        escaped_prevented = max(0, static_fn - full_fn)

    return {
        "total_components": total_components,
        "total_records": total_records,
        "decisions": decisions,
        "anomaly_rate": round(anomalous / total_records * 100, 2),
        "escaped_defects_prevented": escaped_prevented,
    }
