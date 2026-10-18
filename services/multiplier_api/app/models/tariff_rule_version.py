# app/models/tariff_rule_version.py
from datetime import date
from typing import Any, Dict

from sqlalchemy import Date, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TariffRuleVersion(Base):
    __tablename__ = "tariff_rule_version"

    rule_version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    rules: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
