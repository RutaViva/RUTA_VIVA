# services/multiplier_api/tests/test_api.py
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db
from app.services import service_complaint_service
from app.repositories import service_complaint_repo, trip_request_repo

client = TestClient(app)


def test_health_check():
    """Verifica que el endpoint /health responde correctamente."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_zone_id_out_of_bounds_validation():
    """F2 tiene 265 zonas; FastAPI debe responder 422 si queda fuera de rango (ge=1, le=265)."""
    # Zona 0 inválida
    response_zero = client.get("/zones/0/multiplier")
    assert response_zero.status_code == 422

    # Zona 300 fuera de rango
    response_large = client.get("/zones/300/multiplier")
    assert response_large.status_code == 422


def test_audit_endpoint_security_rnf06():
    """RNF-06: La API de auditoría solo es accesible con credenciales de rol auditor (403 si falta)."""
    fake_uuid = "00000000-0000-0000-0000-000000000000"

    # Petición sin credenciales -> 403 Forbidden
    response_unauthorized = client.get(f"/audit/{fake_uuid}")
    assert response_unauthorized.status_code == 403
    assert "Acceso denegado" in response_unauthorized.json()["detail"]

    # Petición con credenciales incorrectas -> 403 Forbidden
    response_wrong = client.get(
        f"/audit/{fake_uuid}",
        headers={"X-Auditor-Role": "passenger", "X-Auditor-Key": "wrong-key"},
    )
    assert response_wrong.status_code == 403

    # Petición con credenciales correctas -> pasa la barrera de autenticación (responde 404 si el viaje no existe)
    response_authorized = client.get(
        f"/audit/{fake_uuid}",
        headers={"X-Auditor-Role": "auditor"},
    )
    assert response_authorized.status_code == 404


def test_create_complaint_for_existing_trip(monkeypatch):
    trip_id = uuid.uuid4()
    complaint_id = uuid.uuid4()
    created_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    calls = []

    def create_complaint(db, trip_id, category):
        calls.append((db, trip_id, category))
        return SimpleNamespace(
            complaint_id=complaint_id,
            trip_id=trip_id,
            created_at=created_at,
            category=category,
        )

    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: "test-db")
    monkeypatch.setattr(
        service_complaint_service, "create_complaint", create_complaint
    )

    response = client.post(
        f"/trip-requests/{trip_id}/complaints",
        json={"category": "service"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "complaint_id": str(complaint_id),
        "trip_id": str(trip_id),
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "category": "service",
    }
    assert calls == [("test-db", trip_id, "service")]
    app.dependency_overrides.pop(get_db, None)


def test_create_complaint_returns_404_for_missing_trip(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: "test-db")
    monkeypatch.setattr(
        service_complaint_service, "create_complaint", lambda *args, **kwargs: None
    )

    response = client.post(
        f"/trip-requests/{uuid.uuid4()}/complaints",
        json={"category": "fare"},
    )

    assert response.status_code == 404
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    "payload",
    [
        {"category": "arbitrary"},
        {"category": "service", "description": "free text is not accepted"},
    ],
)
def test_create_complaint_rejects_unsupported_input(payload):
    response = client.post(
        f"/trip-requests/{uuid.uuid4()}/complaints",
        json=payload,
    )

    assert response.status_code == 422


def test_complaint_service_persists_only_for_existing_trip(monkeypatch):
    trip_id = uuid.uuid4()
    captured = []

    monkeypatch.setattr(
        trip_request_repo, "get_by_id", lambda db, requested_id: object()
    )

    def create(db, complaint):
        captured.append(complaint)
        return complaint

    monkeypatch.setattr(service_complaint_repo, "create", create)
    complaint = service_complaint_service.create_complaint(
        object(), trip_id, "safety"
    )

    assert complaint.trip_id == trip_id
    assert complaint.category == "safety"
    assert len(captured) == 1


def test_complaint_service_does_not_persist_missing_trip(monkeypatch):
    monkeypatch.setattr(trip_request_repo, "get_by_id", lambda db, trip_id: None)
    monkeypatch.setattr(
        service_complaint_repo,
        "create",
        lambda *args: pytest.fail("No debe persistir para un viaje inexistente"),
    )

    assert (
        service_complaint_service.create_complaint(
            object(), uuid.uuid4(), "other"
        )
        is None
    )
