# services/pressure_worker/tests/test_pressure_rules.py
from datetime import datetime, timezone
import pytest

from pressure_calculator import (
    calculate_base_step,
    apply_rain_step,
    apply_regulatory_caps,
)


def test_rn03_pressure_escalation_steps():
    """RN-03: Multiplicador de tarifa según índice de presión."""
    # Menor a 1.2 -> 1.0
    assert calculate_base_step(0.5) == 1.0
    assert calculate_base_step(1.19) == 1.0

    # 1.2 a 2.0 -> 1.2
    assert calculate_base_step(1.2) == 1.2
    assert calculate_base_step(1.8) == 1.2
    assert calculate_base_step(2.0) == 1.2

    # 2.0 a 3.0 -> 1.5
    assert calculate_base_step(2.01) == 1.5
    assert calculate_base_step(2.5) == 1.5
    assert calculate_base_step(3.0) == 1.5

    # Mayor a 3.0 -> 1.8
    assert calculate_base_step(3.1) == 1.8
    assert calculate_base_step(5.0) == 1.8


def test_rn04_rain_penalty_step():
    """RN-04: Si llueve más de 2 mm/h, el multiplicador sube un escalón adicional."""
    assert apply_rain_step(1.0) == 1.2
    assert apply_rain_step(1.2) == 1.5
    assert apply_rain_step(1.5) == 1.8
    assert apply_rain_step(1.8) == 2.0
    assert apply_rain_step(2.0) == 2.0  # Ya en el máximo


def test_rn05_absolute_and_night_caps():
    """RN-05: El multiplicador nunca supera 2.0 y entre 22:00 y 05:00 nunca supera 1.5."""
    # Franja diurna (14:00 NYC = 18:00 UTC)
    day_utc = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)
    assert apply_regulatory_caps(2.5, day_utc) == 2.0
    assert apply_regulatory_caps(1.8, day_utc) == 1.8

    # Franja nocturna (23:30 NYC = 03:30 UTC del día siguiente)
    night_utc = datetime(2026, 10, 16, 3, 30, tzinfo=timezone.utc)
    assert apply_regulatory_caps(1.8, night_utc) == 1.5
    assert apply_regulatory_caps(2.0, night_utc) == 1.5
    assert apply_regulatory_caps(1.2, night_utc) == 1.2


def test_ca02_combined_case_acceptance():
    """CA-02: A las 23:30 con presión 3,5 y lluvia de 5 mm/h, el multiplicador devuelto es 1,5."""
    pressure = 3.5
    rain_mm_h = 5.0
    # 23:30 NYC -> 03:30 UTC
    current_time_utc = datetime(2026, 10, 16, 3, 30, tzinfo=timezone.utc)

    # 1. Base step para presión 3.5 (RN-03: > 3.0 -> 1.8)
    base_mult = calculate_base_step(pressure)
    assert base_mult == 1.8

    # 2. Lluvia 5 mm/h > 2.0 mm/h (RN-04: sube un escalón 1.8 -> 2.0)
    rain_mult = apply_rain_step(base_mult) if rain_mm_h > 2.0 else base_mult
    assert rain_mult == 2.0

    # 3. Tope nocturno a las 23:30 (RN-05: máx 1.5 entre 22:00 y 05:00)
    final_mult = apply_regulatory_caps(rain_mult, current_time_utc)
    assert final_mult == 1.5
