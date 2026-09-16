from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import utcnow


class MonitoringTelemetryLatest(Base):
    """Latest telemetry for one remote monitoring assignment.

    v0.3 stored a single agentless telemetry row per Device. That allowed one
    remote method (for example SNMP) to overwrite fields collected by another
    method (for example SSH). v0.4 scopes raw/latest telemetry to the assignment
    first and maintains the old device-level row only as a compatibility
    aggregate for existing Prometheus/UI code.
    """

    __tablename__ = "monitoring_telemetry_latest"

    assignment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agentless_monitors.id", ondelete="CASCADE"),
        primary_key=True,
    )
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(32), index=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, default=utcnow
    )
    cpu_usage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_used_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_usage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    process_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disks: Mapped[list] = mapped_column(JSON, default=list)
    interfaces: Mapped[list] = mapped_column(JSON, default=list)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
