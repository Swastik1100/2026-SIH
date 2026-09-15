"""API smoke tests for all FastAPI endpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def client():
    """Create test client; train pipeline if models not present."""
    from app.main import app
    from app.services.pipeline import get_pipeline, MODELS_DIR
    from app.core.config import get_config
    from app.data.generator import generate_dataset, generate_demo_components
    from app.data.database import init_db

    init_db()

    # If no trained models, run a mini training session
    pipeline = get_pipeline()
    if not pipeline._trained:
        config = get_config()
        df = generate_dataset(config)
        pipeline.train(df)
        # Persist demo data
        demo_df = generate_demo_components(config)
        pipeline.screen_dataframe(demo_df, persist=True)

    return TestClient(app)


SAMPLE_MEASUREMENTS = [
    {
        "component_id": "TEST-001",
        "lot_id": "LOT-TEST",
        "parameter": "leakage_current",
        "value_0h": 10.5,
        "value_24h": 18.2,
        "value_96h": 32.0,
        "value_168h": 45.1,
        "spec_min": 0.0,
        "spec_max": 50.0,
    },
    {
        "component_id": "TEST-001",
        "lot_id": "LOT-TEST",
        "parameter": "iddq",
        "value_0h": 1.2,
        "value_24h": 1.3,
        "value_96h": 1.4,
        "value_168h": 1.5,
        "spec_min": 0.1,
        "spec_max": 5.0,
    },
]


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_returns_version(self, client):
        response = client.get("/health")
        assert "version" in response.json()


class TestPredictEndpoint:
    def test_predict_returns_200(self, client):
        response = client.post("/predict", json={"measurements": SAMPLE_MEASUREMENTS})
        assert response.status_code == 200

    def test_predict_returns_results_list(self, client):
        response = client.post("/predict", json={"measurements": SAMPLE_MEASUREMENTS})
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) == len(SAMPLE_MEASUREMENTS)

    def test_predict_result_has_required_fields(self, client):
        response = client.post("/predict", json={"measurements": SAMPLE_MEASUREMENTS})
        result = response.json()["results"][0]
        for field in ["component_id", "lot_id", "parameter", "anomaly", "drift", "decision", "explanation"]:
            assert field in result, f"Missing field: {field}"

    def test_predict_decision_is_valid(self, client):
        response = client.post("/predict", json={"measurements": SAMPLE_MEASUREMENTS})
        for result in response.json()["results"]:
            assert result["decision"]["decision"] in ("PASS", "WATCH", "REVIEW", "REJECT")

    def test_predict_explanation_non_empty(self, client):
        response = client.post("/predict", json={"measurements": SAMPLE_MEASUREMENTS})
        for result in response.json()["results"]:
            assert len(result["explanation"]) > 20


class TestAnomalyEndpoint:
    def test_anomaly_returns_200(self, client):
        response = client.post("/anomaly", json={"measurements": SAMPLE_MEASUREMENTS})
        assert response.status_code == 200

    def test_anomaly_returns_list(self, client):
        response = client.post("/anomaly", json={"measurements": SAMPLE_MEASUREMENTS})
        data = response.json()
        assert isinstance(data, list)


class TestDriftEndpoint:
    def test_drift_returns_200(self, client):
        response = client.post("/drift", json={"measurements": SAMPLE_MEASUREMENTS})
        assert response.status_code == 200

    def test_drift_returns_list(self, client):
        response = client.post("/drift", json={"measurements": SAMPLE_MEASUREMENTS})
        data = response.json()
        assert isinstance(data, list)


class TestScreenEndpoint:
    def test_screen_returns_200(self, client):
        response = client.post("/screen", json={"measurements": SAMPLE_MEASUREMENTS})
        assert response.status_code == 200

    def test_screen_returns_count(self, client):
        response = client.post("/screen", json={"measurements": SAMPLE_MEASUREMENTS})
        data = response.json()
        assert "count" in data
        assert "results" in data


class TestMetricsEndpoint:
    def test_metrics_returns_200(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_has_expected_structure(self, client):
        response = client.get("/metrics")
        data = response.json()
        assert isinstance(data, dict)


class TestDashboardStatsEndpoint:
    def test_dashboard_stats_returns_200(self, client):
        response = client.get("/dashboard-stats")
        assert response.status_code == 200

    def test_dashboard_stats_has_fields(self, client):
        response = client.get("/dashboard-stats")
        data = response.json()
        # Should have total_components (if data exists) or 0
        assert "total_components" in data or data.get("total") == 0


class TestScreeningResultsEndpoint:
    def test_screening_results_returns_200(self, client):
        response = client.get("/screening-results")
        assert response.status_code == 200

    def test_screening_results_is_list(self, client):
        response = client.get("/screening-results")
        data = response.json()
        assert isinstance(data, list)


class TestComponentEndpoint:
    def test_missing_component_returns_404(self, client):
        response = client.get("/component/NONEXISTENT-99999")
        assert response.status_code == 404

    def test_existing_component_returns_200(self, client):
        """After screening, demo components should be retrievable."""
        # C003 should be in DB after fixture setup
        response = client.get("/component/C003")
        if response.status_code == 404:
            pytest.skip("C003 not in DB — run pipeline first")
        assert response.status_code == 200
        data = response.json()
        assert data["component_id"] == "C003"


class TestLotEndpoint:
    def test_missing_lot_returns_404(self, client):
        response = client.get("/lot/LOT-NONEXISTENT")
        assert response.status_code == 404

    def test_existing_lot_returns_200(self, client):
        """Demo lot should be in DB after fixture setup."""
        response = client.get("/lot/DEMO-LOT")
        if response.status_code == 404:
            pytest.skip("DEMO-LOT not in DB — run pipeline first")
        assert response.status_code == 200
        data = response.json()
        assert data["lot_id"] == "DEMO-LOT"
        assert "component_count" in data
        assert "statistics" in data
