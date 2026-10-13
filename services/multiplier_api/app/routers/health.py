# app/routers/health.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live():
    # "Estoy vivo": no toca la BD (separado de "ready" a propósito).
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    # "Mi dependencia funciona": el ALB lo usa y valida PostgreSQL.
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok"}