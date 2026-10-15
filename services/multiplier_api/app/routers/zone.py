# app/routers/zones.py
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.zone import NameZone
from app.services import zone_service

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("/{zone_id}", response_model=NameZone)
def read_zone(
    # F2 tiene 265 zonas; FastAPI responde 422 si queda fuera de rango.
    zone_id: int = Path(ge=1, le=265),
    db: Session = Depends(get_db),
):
    zone = zone_service.get_zone(db, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="zone not found")
    return zone