# app/main.py
from fastapi import FastAPI

from app.routers import health, multiplier
from app.routers import health, multiplier, zone

app = FastAPI(title="RutaViva multiplier-api")
app.include_router(zone.router)
app.include_router(health.router)
app.include_router(multiplier.router)