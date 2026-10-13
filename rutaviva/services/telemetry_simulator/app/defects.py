# defects.py
import random
from dataclasses import dataclass
from typing import List, Tuple

from config import (
    OUTSIDE_MIN_LAT,
    OUTSIDE_MAX_LAT,
    OUTSIDE_MIN_LON,
    OUTSIDE_MAX_LON,
)


@dataclass(frozen=True)
class DefectPlan:
    silent_ids: frozenset[str]
    out_of_city_ids: frozenset[str]


def plan_defects(
    vehicle_ids: List[str],
    silent_pct: float,
    out_of_city_pct: float,
    rng: random.Random = None,
) -> DefectPlan:
    """
    Planifica qué vehículos serán defectuosos:
    - silent_pct%: dejan de reportar (no emiten telemetría).
    - out_of_city_pct%: reportan coordenadas anómalas fuera de la ciudad.
    Ambos conjuntos son disjuntos.
    """
    if silent_pct + out_of_city_pct > 100:
        raise ValueError("silent_pct + out_of_city_pct no puede superar 100")

    if rng is None:
        rng = random.Random()

    shuffled = list(vehicle_ids)
    rng.shuffle(shuffled)

    total = len(shuffled)
    silent_count = round(total * silent_pct / 100)
    outside_count = round(total * out_of_city_pct / 100)

    silent_ids = frozenset(shuffled[:silent_count])
    out_of_city_ids = frozenset(shuffled[silent_count : silent_count + outside_count])

    return DefectPlan(silent_ids=silent_ids, out_of_city_ids=out_of_city_ids)


def out_of_city_position(rng: random.Random = None) -> Tuple[float, float]:
    """Genera coordenadas válidas en formato pero fuera de los límites de NYC."""
    if rng is None:
        rng = random.Random()

    lat = rng.uniform(OUTSIDE_MIN_LAT, OUTSIDE_MAX_LAT)
    lon = rng.uniform(OUTSIDE_MIN_LON, OUTSIDE_MAX_LON)
    return round(lat, 6), round(lon, 6)
