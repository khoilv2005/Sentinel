from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import uid, utcnow


class CollectorTelemetryLatest(Base):
    """Latest telemetry for one remote monitoring assignment.

    The legacy AgentlessTelemetryLatest table is keyed only by device_id, which
    means two methods on the same asset can overwrite each other. This table is
    keyed by monitor_id so WinRM/SSH/SNMP keep independent observations. The
    legacy aggregate remains populated during the v0.4 transition for existing
    Host Detail and Prometheus compatibility.
    """

    __tablename__ = "collector_telemetry_latest"

    monitor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agentless_monitors.id", ondelete="CASCADE"),
        primary_key=True,
    )
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("devices.id", ondelete="CASCADE"),
        index=True,
    )
    method: Mapped[str] = mapped_column(String(32), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=utcnow)
    cpu_usage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_used_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_usage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    process_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disks: Mapped[list] = mapped_column(JSON, default=list)
    interfaces: Mapped[list] = mapped_column(JSON, default=list)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
