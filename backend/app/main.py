"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.data.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — runs startup logic then yields."""
    init_db()
    yield
    # Teardown (if needed) goes here


app = FastAPI(
    title="BurnSight AI — Burn-In Anomaly Detection API",
    description=(
        "AI-driven anomaly detection for electronic component burn-in & environmental stress screening. "
        "Catches latent defects that traditional static-limit screening misses."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://frontend:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
