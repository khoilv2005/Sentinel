import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid.uuid4())


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    ip_address: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    mac_address: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    os_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    device_class: Mapped[str] = mapped_column(String(64), default="unknown", index=True)
    state: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_ports: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    site: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    agent_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    agent_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snmp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    snmp_module: Mapped[str] = mapped_column(String(64), default="if_mib")
    snmp_auth: Mapped[str] = mapped_column(String(64), default="public_v2")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class NetworkInterface(Base):
    __tablename__ = "device_interfaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    mac_address: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    speed_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admin_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    oper_status: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ScanJob(Base):
    __tablename__ = "scan_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    cidr: Mapped[str] = mapped_column(String(64), index=True)
    site: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    discovered: Mapped[int] = mapped_column(Integer, default=0)
    scanned: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertRule(Base):
    __tablename__ = "alert_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    metric: Mapped[str] = mapped_column(String(255))
    operator: Mapped[str] = mapped_column(String(8), default=">")
    warning_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    critical_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=300)
    match_labels: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(32), default="info", index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class TopologyEdge(Base):
    __tablename__ = "topology_edges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    source_device_id: Mapped[str] = mapped_column(String(36), index=True)
    target_device_id: Mapped[str] = mapped_column(String(36), index=True)
    relation: Mapped[str] = mapped_column(String(64), default="network")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# v0.2.3 agent management tables are intentionally separate from Device so an
# existing v0.2.2 database upgrades via CREATE TABLE without ALTER TABLE.
class AgentPolicy(Base):
    __tablename__ = "agent_policies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentEnrollmentToken(Base):
    __tablename__ = "agent_enrollment_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_prefix: Mapped[str] = mapped_column(String(24), index=True)
    policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_policies.id"), index=True)
    site: Mapped[str | None] = mapped_column(String(160), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ManagedAgent(Base):
    __tablename__ = "managed_agents"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), unique=True, index=True)
    credential_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255), index=True)
    os_name: Mapped[str] = mapped_column(String(64), index=True)
    arch: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(64))
    policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_policies.id"), index=True)
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    site: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_checkin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentTelemetryLatest(Base):
    __tablename__ = "agent_telemetry_latest"
    agent_id: Mapped[str] = mapped_column(String(48), ForeignKey("managed_agents.id", ondelete="CASCADE"), primary_key=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cpu_usage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_used_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_usage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    process_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disks: Mapped[list] = mapped_column(JSON, default=list)
    interfaces: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Problem(Base):
    __tablename__ = "problems"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    service_key: Mapped[str] = mapped_column(String(255), index=True)
    service_name: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(32), default="warning", index=True)
    state: Mapped[str] = mapped_column(String(32), default="open", index=True)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(160), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(160), default="system", index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    object_type: Mapped[str] = mapped_column(String(128), index=True)
    object_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(255), index=True)
    device_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True)
    site: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    suppress_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    exclude_from_sla: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(160), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationChannel(Base):
    __tablename__ = "notification_channels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    channel_type: Mapped[str] = mapped_column(String(64), default="webhook", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SlaDefinition(Base):
    __tablename__ = "sla_definitions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    target_percent: Mapped[float] = mapped_column(Float, default=99.9)
    device_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True)
    site: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocalUser(Base):
    __tablename__ = "local_users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(32), default="viewer", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)



class CredentialProfile(Base):
    __tablename__ = "credential_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    credential_type: Mapped[str] = mapped_column(String(32), index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    secret_encrypted: Mapped[str] = mapped_column(Text)
    options_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentlessMonitor(Base):
    __tablename__ = "agentless_monitors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(32), index=True)
    credential_id: Mapped[str] = mapped_column(String(36), ForeignKey("credential_profiles.id"), index=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AgentlessTelemetryLatest(Base):
    __tablename__ = "agentless_telemetry_latest"
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
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
