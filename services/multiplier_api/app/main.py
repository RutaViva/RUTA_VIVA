# app/main.py
import sys
from pathlib import Path

# Permitir resolución de imports 'from app...' tanto desde la raíz del repo como dentro del microservicio o Docker
_service_dir = Path(__file__).resolve().parent.parent
if str(_service_dir) not in sys.path:
    sys.path.insert(0, str(_service_dir))

from app.routers import audit, health, multiplier, trip_request, zone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="RutaViva Multiplier & Mobility API",
    description="API de cotización de tarifas dinámicas, registro de viajes y auditoría transaccional.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(zone.router)
app.include_router(multiplier.router)
app.include_router(trip_request.router)
app.include_router(audit.router)
