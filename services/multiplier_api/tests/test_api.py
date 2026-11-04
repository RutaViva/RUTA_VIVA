# services/multiplier_api/tests/test_api.py
import concurrent.futures
import uuid
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal, get_db
from app.main import app
from app.models.zone_state import ZoneStateHistory
from app.repositories import service_complaint_repo, trip_request_repo
from app.services import service_complaint_service

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


def test_create_trip_request_success_ca11():
    """
    HU-01 / CA 1.1:
    Given a valid zone,
    When a request is created (POST),
    Then the API responds with the current multiplier for that zone at that time.
    """
    payload = {"zone_id": 161, "base_fare": 25.0}
    response = client.post("/trip-requests", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "trip_id" in data
    assert data["zone_id"] == 161
    assert "multiplier" in data
    assert data["multiplier"] >= 1.0
    assert "status" in data
    assert data["status"] == "created"
    assert data["charged_fare"] == round(data["base_fare"] * data["multiplier"], 2)


def test_cancel_trip_request_preserves_record_ca12():
    """
    HU-01 / CA 1.2:
    Given a created request,
    When the passenger decides not to proceed,
    Then a cancellation operation exists that marks it as such (without deleting it).
    """
    # 1. Crear la solicitud
    create_resp = client.post("/trip-requests", json={"zone_id": 161, "base_fare": 20.0})
    assert create_resp.status_code == 201
    trip_id = create_resp.json()["trip_id"]

    # 2. Cancelar la solicitud (retorna status='cancelled' sin borrar el registro)
    cancel_resp = client.post(f"/trip-requests/{trip_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["trip_id"] == trip_id
    assert cancel_resp.json()["status"] == "cancelled"

    # 3. Verificar que el registro aún existe en la base de datos (auditoría inmutable RNF-06)
    audit_resp = client.get(f"/audit/{trip_id}", headers={"X-Auditor-Role": "auditor"})
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["trip_id"] == trip_id
    assert audit_data["charged_fare"] > 0


def test_concurrent_burst_requests_ca13():
    """
    HU-01 / CA 1.3:
    Given the load testing scenario,
    When configurable bursts are generated (e.g., end of a concert),
    Then the API sustains the volume without crashing.
    """
    burst_count = 25
    payload = {"zone_id": 161, "base_fare": 18.5}

    def _send_request():
        return client.post("/trip-requests", json=payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_send_request) for _ in range(burst_count)]
        responses = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(responses) == burst_count
    for resp in responses:
        assert resp.status_code == 201
        assert resp.json()["multiplier"] >= 1.0


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


def test_underserved_zones_rf05():
    """
    RF-05 / RN-08:
    Detectar zonas desatendidas (tiempo de espera > 12 min en 3 intervalos consecutivos)
    y sugerir redistribución de flota a conductores.
    """
    db = SessionLocal()
    now_utc = datetime.now(UTC)
    # Insertar 3 intervalos consecutivos con espera estimada > 12 min para la zona 10
    for i in range(3):
        h = ZoneStateHistory(
            zone_id=10,
            interval_start=now_utc - timedelta(seconds=30 * (3 - i)),
            requests=50,
            free_vehicles=1,
            pressure_index=5.0,
            multiplier=1.8,
            estimated_wait_minutes=15.0 + i,
        )
        db.merge(h)
    db.commit()
    db.close()

    resp = client.get("/zones/underserved")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Verificar que la zona 10 aparece en la lista de zonas desatendidas
    matched = [z for z in data if z["zone_id"] == 10]
    assert len(matched) == 1
    assert matched[0]["consecutive_intervals"] >= 3
    assert matched[0]["avg_estimated_wait_minutes"] >= 12.0
    assert matched[0]["recommended_additional_vehicles"] > 0


def test_recalculate_tariffs_period_rf08():
    """
    RF-08 / RNF-06:
    Permitir versionar las reglas de tarifa y recalcular un periodo con una versión específica.
    Protegido por rol de auditor.
    """
    # 1. Crear un viaje para garantizar que hay transacciones en el periodo
    create_resp = client.post("/trip-requests", json={"zone_id": 161, "base_fare": 20.0})
    assert create_resp.status_code == 201

    payload = {
        "start_date": "2020-01-01T00:00:00Z",
        "end_date": "2030-01-01T00:00:00Z",
        "rule_version_id": 1,
    }

    # 2. Sin credenciales de auditor -> 403 Forbidden
    unauth_resp = client.post("/audit/recalculate", json=payload)
    assert unauth_resp.status_code == 403

    # 3. Con credenciales válidas -> 200 OK con simulación comparativa
    auth_resp = client.post(
        "/audit/recalculate",
        json=payload,
        headers={"X-Auditor-Role": "auditor"},
    )
    assert auth_resp.status_code == 200
    data = auth_resp.json()
    assert data["rule_version_id"] == 1
    assert data["total_trips_evaluated"] >= 1
    assert data["original_total_revenue"] > 0
    assert data["recalculated_total_revenue"] > 0
    assert "percentage_change" in data
