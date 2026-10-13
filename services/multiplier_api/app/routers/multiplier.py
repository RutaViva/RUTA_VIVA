# app/routers/multiplier.py
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.multiplier import MultiplierResponse
from app.services import multiplier_service

router = APIRouter(prefix="/zones", tags=["multiplier"])


@router.get("/{zone_id}/multiplier", response_model=MultiplierResponse)
def read_multiplier(
    # F2 tiene 265 zonas; FastAPI responde 422 si queda fuera de rango.
    zone_id: int = Path(ge=1, le=265),
    db: Session = Depends(get_db),
):
    result = multiplier_service.get_current_multiplier(db, zone_id)
    if result is None:
        raise HTTPException(status_code=404, detail="zone not found")
    return result