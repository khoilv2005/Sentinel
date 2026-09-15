from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DeviceCreate(BaseModel):
    ip_address: str
    hostname: str | None = None
    mac_address: str | None = None
    device_class: str = "unknown"
    site: str | None = None
    tags: list[str] = Field(default_factory=list)
    snmp_enabled: bool = False
    snmp_module: str = "if_mib"
    snmp_auth: str = "public_v2"


class DevicePatch(BaseModel):
    hostname: str | None = None
    mac_address: str | None = None
    vendor: str | None = None
    model: str | None = None
    os_name: str | None = None
    device_class: str | None = None
    state: str | None = None
    site: str | None = None
    tags: list[str] | None = None
    snmp_enabled: bool | None = None
    snmp_module: str | None = None
    snmp_auth: str | None = None


class DeviceOut(ORMModel):
    id: str
    ip_address: str
    hostname: str | None
    mac_address: str | None
    vendor: str | None
    model: str | None
    os_name: str | None
    device_class: str
    state: str
    latency_ms: float | None
    open_ports: list
    tags: list
    site: str | None
    agent_enabled: bool
    agent_endpoint: str | None
    agent_version: str | None
    agent_last_seen: datetime | None
    snmp_enabled: bool
    snmp_module: str
    snmp_auth: str
    first_seen: datetime
    last_seen: datetime | None


class ScanCreate(BaseModel):
    cidr: str
    site: str | None = None


class ScanOut(ORMModel):
    id: str
    cidr: str
    site: str | None
    status: str
    discovered: int
    scanned: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


# Legacy v0.2.2 pull-agent compatibility.
class AgentRegister(BaseModel):
    device_id: str | None = None
    hostname: str
    advertise_address: str | None = None
    os_name: str | None = None
    arch: str | None = None
    version: str
    site: str | None = None
    tags: list[str] = Field(default_factory=list)


class AgentRegisterResponse(BaseModel):
    device_id: str
    scrape_endpoint: str


class Heartbeat(BaseModel):
    device_id: str
    version: str | None = None


class AgentPolicyCreate(BaseModel):
    name: str
    telemetry_interval_seconds: int = Field(15, ge=5, le=3600)
    checkin_interval_seconds: int = Field(30, ge=10, le=3600)
    collect_cpu: bool = True
    collect_memory: bool = True
    collect_disk: bool = True
    collect_network: bool = True
    collect_process_count: bool = True


class AgentPolicyOut(ORMModel):
    id: str
    name: str
    version: int
    config: dict
    is_default: bool
    created_at: datetime
    updated_at: datetime


class EnrollmentTokenCreate(BaseModel):
    policy_id: str | None = None
    site: str | None = None
    expires_in_minutes: int = Field(30, ge=1, le=43200)
    max_uses: int = Field(1, ge=1, le=10000)


class EnrollmentTokenCreated(BaseModel):
    id: str
    token: str
    token_prefix: str
    policy_id: str
    site: str | None
    expires_at: datetime
    max_uses: int


class EnrollmentTokenOut(ORMModel):
    id: str
    token_prefix: str
    policy_id: str
    site: str | None
    expires_at: datetime
    max_uses: int
    used_count: int
    revoked: bool
    created_at: datetime


class AgentEnrollRequest(BaseModel):
    enrollment_token: str = Field(min_length=16, max_length=256)
    hostname: str = Field(min_length=1, max_length=255)
    os_name: str = Field(min_length=1, max_length=64)
    arch: str = Field(min_length=1, max_length=32)
    version: str = Field(min_length=1, max_length=64)
    ip_address: str | None = Field(default=None, max_length=64)
    site: str | None = Field(default=None, max_length=160)
    tags: list[str] = Field(default_factory=list, max_length=64)


class AgentEnrollResponse(BaseModel):
    agent_id: str
    device_id: str
    agent_token: str
    policy_id: str
    policy_version: int
    policy: dict


class AgentCheckinRequest(BaseModel):
    hostname: str | None = Field(default=None, max_length=255)
    version: str | None = Field(default=None, max_length=64)
    ip_address: str | None = Field(default=None, max_length=64)


class AgentCheckinResponse(BaseModel):
    status: str
    policy_id: str
    policy_version: int
    policy: dict
    server_time: datetime


class DiskMetric(BaseModel):
    mountpoint: str = Field(min_length=1, max_length=512)
    fstype: str = Field("", max_length=64)
    total_bytes: int = Field(0, ge=0)
    used_bytes: int = Field(0, ge=0)
    usage_percent: float = Field(0, ge=0, le=100)


class InterfaceMetric(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    receive_bytes_total: int = Field(0, ge=0)
    transmit_bytes_total: int = Field(0, ge=0)


class AgentTelemetryIn(BaseModel):
    collected_at: datetime
    cpu_usage_percent: float | None = Field(default=None, ge=0, le=100)
    memory_total_bytes: int | None = Field(default=None, ge=0)
    memory_used_bytes: int | None = Field(default=None, ge=0)
    memory_usage_percent: float | None = Field(default=None, ge=0, le=100)
    uptime_seconds: int | None = Field(default=None, ge=0)
    process_count: int | None = Field(default=None, ge=0)
    disks: list[DiskMetric] = Field(default_factory=list, max_length=128)
    interfaces: list[InterfaceMetric] = Field(default_factory=list, max_length=256)


class ManagedAgentOut(BaseModel):
    id: str
    device_id: str
    hostname: str
    os_name: str
    arch: str
    version: str
    policy_id: str
    policy_version: int
    site: str | None
    tags: list
    enrolled_at: datetime
    last_checkin: datetime | None
    last_ip: str | None
    revoked: bool
    online: bool


class AlertRuleCreate(BaseModel):
    name: str
    metric: str
    operator: str = ">"
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    duration_seconds: int = 300
    match_labels: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class AlertRuleOut(ORMModel):
    id: str
    name: str
    metric: str
    operator: str
    warning_threshold: float | None
    critical_threshold: float | None
    duration_seconds: int
    match_labels: dict
    enabled: bool


class EventOut(ORMModel):
    id: str
    device_id: str | None
    severity: str
    event_type: str
    message: str
    details: dict
    created_at: datetime


class EdgeCreate(BaseModel):
    source_device_id: str
    target_device_id: str
    relation: str = "network"
    metadata_json: dict = Field(default_factory=dict)


class EdgeOut(ORMModel):
    id: str
    source_device_id: str
    target_device_id: str
    relation: str
    metadata_json: dict
    created_at: datetime


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=1, max_length=512)


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: dict


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=8, max_length=512)
    role: Literal["admin", "operator", "viewer"] = "viewer"


class UserPatch(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=512)
    role: Literal["admin", "operator", "viewer"] | None = None
    enabled: bool | None = None


class UserOut(ORMModel):
    id: str
    username: str
    role: str
    enabled: bool
    last_login: datetime | None
    created_at: datetime


class ProblemOut(ORMModel):
    id: str
    device_id: str
    service_key: str
    service_name: str
    severity: str
    state: str
    title: str
    message: str
    current_value: float | None
    threshold: float | None
    opened_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by: str | None


class MaintenanceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    device_id: str | None = None
    site: str | None = None
    starts_at: datetime
    ends_at: datetime
    suppress_notifications: bool = True
    exclude_from_sla: bool = True


class MaintenanceOut(ORMModel):
    id: str
    name: str
    device_id: str | None
    site: str | None
    starts_at: datetime
    ends_at: datetime
    suppress_notifications: bool
    exclude_from_sla: bool
    created_by: str
    created_at: datetime


class NotificationChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    channel_type: Literal["webhook", "email", "slack", "teams", "telegram"] = "webhook"
    enabled: bool = True
    config: dict = Field(default_factory=dict)


class NotificationChannelOut(ORMModel):
    id: str
    name: str
    channel_type: str
    enabled: bool
    config: dict
    created_at: datetime
    updated_at: datetime


class SlaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    target_percent: float = Field(default=99.9, ge=0, le=100)
    device_id: str | None = None
    site: str | None = None
    enabled: bool = True


class SlaOut(ORMModel):
    id: str
    name: str
    target_percent: float
    device_id: str | None
    site: str | None
    enabled: bool
    created_at: datetime


class AuditOut(ORMModel):
    id: str
    actor: str
    action: str
    object_type: str
    object_id: str | None
    message: str
    details: dict
    created_at: datetime


class RulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    metric: str | None = None
    operator: str | None = None
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    match_labels: dict | None = None
    enabled: bool | None = None


class PolicyPatch(BaseModel):
    telemetry_interval_seconds: int | None = Field(default=None, ge=5, le=3600)
    checkin_interval_seconds: int | None = Field(default=None, ge=10, le=3600)
    collect_cpu: bool | None = None
    collect_memory: bool | None = None
    collect_disk: bool | None = None
    collect_network: bool | None = None
    collect_process_count: bool | None = None


class TopologyGraphOut(BaseModel):
    nodes: list[dict]
    edges: list[dict]


class ServiceOut(BaseModel):
    host_id: str
    hostname: str
    service_key: str
    service_name: str
    state: str
    value: float | str | None = None
    unit: str | None = None
    message: str
    updated_at: datetime | None = None


class HostSummaryOut(BaseModel):
    id: str
    hostname: str | None
    ip_address: str
    state: str
    device_class: str
    os_name: str | None
    site: str | None
    agent_enabled: bool
    agent_online: bool
    agent_version: str | None
    problem_count: int
    critical_count: int
    warning_count: int
    service_count: int
    last_seen: datetime | None


class HostOverviewOut(BaseModel):
    device: DeviceOut
    agent: ManagedAgentOut | None = None
    telemetry: dict | None = None
    services: list[ServiceOut] = Field(default_factory=list)
    problems: list[ProblemOut] = Field(default_factory=list)
