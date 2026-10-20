# app/schemas/trip_request.py
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class TripCreateRequest(BaseModel):
    """
    Schema para creación/cotización de solicitudes de viaje.
    Permite tanto el envío directo de 'base_fare' como el cálculo automático
    por distancia y tiempo según la Regla de Negocio RN-01.
    """
    zone_id: Optional[int] = Field(None, ge=1, le=265, description="ID de la zona de origen del viaje (1-265)")
    origin_zone_id: Optional[int] = Field(None, ge=1, le=265, description="Alias de zone_id (zona de origen)")
    base_fare: Optional[float] = Field(None, gt=0, description="Tarifa base fija estimada para el viaje en USD")
    passenger_id: Optional[uuid.UUID] = Field(None, description="UUID del pasajero que solicita el servicio")
    destination_zone_id: Optional[int] = Field(None, ge=1, le=265, description="Zona de destino del viaje")
    estimated_distance_km: Optional[float] = Field(None, ge=0, description="Distancia estimada en kilómetros")
    estimated_duration_min: Optional[float] = Field(None, ge=0, description="Duración estimada en minutos")

    @model_validator(mode="after")
    def validate_zone_and_fare(self) -> "TripCreateRequest":
        effective_zone = self.zone_id if self.zone_id is not None else self.origin_zone_id
        if effective_zone is None:
            raise ValueError("Debe especificarse 'zone_id' o 'origin_zone_id' (1-265).")

        # Si no se envía base_fare directa, se calcula con la fórmula RN-01
        if self.base_fare is None:
            km = self.estimated_distance_km or 0.0
            mins = self.estimated_duration_min or 0.0
            # RN-01: Base fija $1.50 + $0.35 por km + $0.15 por minuto
            computed_fare = round(1.50 + (0.35 * km) + (0.15 * mins), 2)
            self.base_fare = max(computed_fare, 1.50)

        self.zone_id = effective_zone
        return self


class TripResponse(BaseModel):
    trip_id: uuid.UUID
    zone_id: int
    requested_at: datetime
    status: str
    base_fare: float
    multiplier: float
    charged_fare: float
    degraded: bool


class TripStatusUpdateRequest(BaseModel):
    status: str = Field(description="Nuevo estado: 'created', 'assigned', 'cancelled'")
