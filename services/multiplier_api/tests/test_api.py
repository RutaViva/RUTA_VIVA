# services/multiplier_api/tests/test_api.py
import pytest
from fastapi.testclient import TestClient

from app.main import app

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
