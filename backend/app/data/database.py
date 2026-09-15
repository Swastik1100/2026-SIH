"""SQLAlchemy database models."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_config


class Base(DeclarativeBase):
    pass


class ScreeningResult(Base):
    __tablename__ = "screening_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    component_id = Column(String(64), index=True, nullable=False)
    lot_id = Column(String(64), index=True, nullable=False)
    parameter = Column(String(64), nullable=False)
    value_0h = Column(Float)
    value_24h = Column(Float)
    value_96h = Column(Float)
    value_168h = Column(Float)
    spec_min = Column(Float)
    spec_max = Column(Float)
    static_result = Column(String(16))
    anomaly_score = Column(Float)
    anomaly_severity = Column(String(16))
    predicted_168h = Column(Float)
    drift_risk = Column(String(16))
    drift_rate = Column(Float)
    final_decision = Column(String(16))
    explanation = Column(Text)
    label = Column(String(32))
    extra = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        cfg = get_config()
        db_url = cfg.get("database", {}).get("url", "sqlite:///./data/burnin.db")

        # Automatically create the folder if using a local SQLite file
        if db_url.startswith("sqlite:///"):
            db_file_path = db_url.replace("sqlite:///", "")
            parent_dir = Path(db_file_path).parent
            if parent_dir and not parent_dir.exists():
                os.makedirs(parent_dir, exist_ok=True)

        _engine = create_engine(db_url, connect_args={"check_same_thread": False})
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)


def get_db():
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()