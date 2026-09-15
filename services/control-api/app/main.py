import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from starlette.responses import Response

from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import (
    AuditEvent,
    AgentEnrollmentToken,
    AgentPolicy,
    AgentTelemetryLatest,
    AgentlessTelemetryLatest,
    AlertRule,
    Device,
    Event,
    ManagedAgent,
    MaintenanceWindow,
    NotificationChannel,
    Problem,
    SlaDefinition,
    LocalUser,
    ScanJob,
    TopologyEdge,
)
from .netutils import parse_private_network
from .schemas import (
    AuditOut,
    AgentCheckinRequest,
    AgentCheckinResponse,
    AgentEnrollRequest,
    AgentEnrollResponse,
    AgentPolicyCreate,
    AgentPolicyOut,
    AgentRegister,
    AgentRegisterResponse,
    AgentTelemetryIn,
    HostOverviewOut,
    HostSummaryOut,
    LoginRequest,
    LoginResponse,
    MaintenanceCreate,
    MaintenanceOut,
    NotificationChannelCreate,
    NotificationChannelOut,
    PolicyPatch,
    ProblemOut,
    RulePatch,
    ServiceOut,
    SlaCreate,
    SlaOut,
    TopologyGraphOut,
    UserCreate,
    UserOut,
    UserPatch,
    AlertRuleCreate,
    AlertRuleOut,
    DeviceCreate,
    DeviceOut,
    DevicePatch,
    EdgeCreate,
    EdgeOut,
    EnrollmentTokenCreate,
    EnrollmentTokenCreated,
    EnrollmentTokenOut,
    EventOut,
    Heartbeat,
    ManagedAgentOut,
    ScanCreate,
    ScanOut,
)
from .security import (
    control_identity,
    create_session_token,
    decode_session_token,
    hash_password,
    hash_token,
    new_agent_id,
    new_agent_token,
    new_enrollment_token,
    require_api_key,
    require_roles,
    require_write,
    verify_password,
)
from .monitoring import all_services, is_agent_online, latest_telemetry_for_device, services_for_device, sync_problems
from .agentless_api import router as agentless_router

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("sentinelview")

Base.metadata.create_all(bind=engine)

DEFAULT_POLICY_CONFIG = {
    "telemetry_interval_seconds": 15,
    "checkin_interval_seconds": 30,
    "collect_cpu": True,
    "collect_memory": True,
    "collect_disk": True,
    "collect_network": True,
    "collect_process_count": True,
}


def utcnow():
    return datetime.now(timezone.utc)


def ensure_bootstrap_data():
    db = SessionLocal()
    try:
        policy = db.execute(select(AgentPolicy).where(AgentPolicy.is_default.is_(True))).scalar_one_or_none()
        if policy is None:
            policy = AgentPolicy(name="Default", config=DEFAULT_POLICY_CONFIG, is_default=True, version=1)
            db.add(policy)
            db.flush()
            logger.info("created default agent policy %s", policy.id)

        defaults = [
            ("CPU utilization", "sentinel_cpu_usage_percent", ">", 80.0, 95.0, 300),
            ("Memory utilization", "sentinel_memory_usage_percent", ">", 85.0, 95.0, 300),
            ("Disk utilization", "sentinel_disk_usage_percent", ">", 85.0, 95.0, 300),
            ("Managed agent availability", "sentinel_agent_up", "<", None, 1.0, 120),
        ]
        for name, metric, operator, warning, critical, duration in defaults:
            exists = db.execute(select(AlertRule).where(AlertRule.metric == metric)).scalar_one_or_none()
            if exists is None:
                db.add(AlertRule(
                    name=name, metric=metric, operator=operator, warning_threshold=warning,
                    critical_threshold=critical, duration_seconds=duration, enabled=True, match_labels={},
                ))

        admin = db.execute(select(LocalUser).where(LocalUser.username == settings.admin_user)).scalar_one_or_none()
        if admin is None:
            db.add(LocalUser(
                username=settings.admin_user, password_hash=hash_password(settings.admin_password),
                role="admin", enabled=True,
            ))
            logger.warning("created bootstrap admin user '%s'; change the default password", settings.admin_user)
        db.commit()
    finally:
        db.close()


ensure_bootstrap_data()

app = FastAPI(
    title="SentinelView Control API",
    version="0.3.0",
    description="SentinelView infrastructure monitoring control plane with first-party operations UI and Fleet-style agents",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
)

app.include_router(agentless_router)

API_REQUESTS = Counter("sentinel_control_api_requests_total", "HTTP requests", ["method", "path", "status"])
DEVICE_GAUGE = Gauge("sentinel_control_devices", "Devices stored in inventory", ["state", "device_class"])
AGENT_UP = Gauge("sentinel_agent_up", "Managed agent is online", ["host_id", "hostname", "site", "os", "arch", "version"])
CPU_USAGE = Gauge("sentinel_cpu_usage_percent", "CPU usage percent", ["host_id", "hostname", "site"])
MEM_TOTAL = Gauge("sentinel_memory_total_bytes", "Total physical memory", ["host_id", "hostname", "site"])
MEM_USED = Gauge("sentinel_memory_used_bytes", "Used physical memory", ["host_id", "hostname", "site"])
MEM_USAGE = Gauge("sentinel_memory_usage_percent", "Memory usage percent", ["host_id", "hostname", "site"])
DISK_TOTAL = Gauge("sentinel_disk_total_bytes", "Disk total bytes", ["host_id", "hostname", "site", "mountpoint", "fstype"])
DISK_USED = Gauge("sentinel_disk_used_bytes", "Disk used bytes", ["host_id", "hostname", "site", "mountpoint", "fstype"])
DISK_USAGE = Gauge("sentinel_disk_usage_percent", "Disk usage percent", ["host_id", "hostname", "site", "mountpoint", "fstype"])
NET_RX = Gauge("sentinel_network_receive_bytes_total", "Network received bytes", ["host_id", "hostname", "site", "interface"])
NET_TX = Gauge("sentinel_network_transmit_bytes_total", "Network transmitted bytes", ["host_id", "hostname", "site", "interface"])
UPTIME = Gauge("sentinel_uptime_seconds", "Host uptime seconds", ["host_id", "hostname", "site"])
PROCESS_COUNT = Gauge("sentinel_process_count", "Running process count", ["host_id", "hostname", "site"])


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if not path.startswith("/metrics"):
        API_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "sentinelview-control", "version": "0.3.0"}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)):
    db.execute(select(Device.id).limit(1)).all()
    return {"status": "ready"}


def add_audit(db: Session, actor: str, action: str, object_type: str, object_id: str | None, message: str, details: dict | None = None):
    db.add(AuditEvent(
        actor=actor, action=action, object_type=object_type, object_id=object_id,
        message=message, details=details or {},
    ))


def set_device_state(db: Session, device: Device, state: str, source: str):
    previous = device.state
    device.state = state
    if previous != state:
        db.add(Event(
            device_id=device.id, severity="critical" if state == "down" else "info",
            event_type="state_change", message=f"{device.hostname or device.ip_address}: {previous} -> {state}",
            details={"from": previous, "to": state, "source": source},
        ))


@app.post("/api/v1/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(select(LocalUser).where(LocalUser.username == payload.username)).scalar_one_or_none()
    if user is None or not user.enabled or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "invalid username or password")
    token, expires_at = create_session_token(user.username, user.role)
    user.last_login = utcnow()
    add_audit(db, user.username, "login", "session", None, "User logged in")
    db.commit()
    return LoginResponse(token=token, expires_at=expires_at, user={"username": user.username, "role": user.role})


@app.get("/api/v1/auth/me")
def auth_me(identity: dict = Depends(control_identity)):
    return identity


@app.get("/api/v1/users", response_model=list[UserOut])
def list_users(identity: dict = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return list(db.execute(select(LocalUser).order_by(LocalUser.username)).scalars())


@app.post("/api/v1/users", response_model=UserOut)
def create_user(payload: UserCreate, identity: dict = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    if db.execute(select(LocalUser).where(LocalUser.username == payload.username)).scalar_one_or_none():
        raise HTTPException(409, "username already exists")
    row = LocalUser(username=payload.username, password_hash=hash_password(payload.password), role=payload.role, enabled=True)
    db.add(row); db.flush()
    add_audit(db, identity["username"], "create", "user", row.id, f"Created user {row.username}", {"role": row.role})
    db.commit(); db.refresh(row)
    return row


@app.patch("/api/v1/users/{user_id}", response_model=UserOut)
def patch_user(user_id: str, payload: UserPatch, identity: dict = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    row = db.get(LocalUser, user_id)
    if row is None: raise HTTPException(404, "user not found")
    values = payload.model_dump(exclude_unset=True)
    if values.get("password"):
        row.password_hash = hash_password(values.pop("password"))
    for key, value in values.items(): setattr(row, key, value)
    add_audit(db, identity["username"], "update", "user", row.id, f"Updated user {row.username}", {"role": row.role, "enabled": row.enabled})
    db.commit(); db.refresh(row)
    return row


def _is_online(last_seen: datetime | None) -> bool:
    if last_seen is None:
        return False
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return last_seen >= utcnow() - timedelta(seconds=settings.agent_online_seconds)


def _refresh_metric_gauges(db: Session):
    DEVICE_GAUGE.clear()
    AGENT_UP.clear(); CPU_USAGE.clear(); MEM_TOTAL.clear(); MEM_USED.clear(); MEM_USAGE.clear()
    DISK_TOTAL.clear(); DISK_USED.clear(); DISK_USAGE.clear(); NET_RX.clear(); NET_TX.clear()
    UPTIME.clear(); PROCESS_COUNT.clear()

    for d in db.execute(select(Device)).scalars():
        DEVICE_GAUGE.labels(d.state, d.device_class).inc()

    agents = list(db.execute(select(ManagedAgent).where(ManagedAgent.revoked.is_(False))).scalars())
    telemetry = {t.agent_id: t for t in db.execute(select(AgentTelemetryLatest)).scalars()}
    for a in agents:
        labels = (a.device_id, a.hostname, a.site or "default")
        AGENT_UP.labels(a.device_id, a.hostname, a.site or "default", a.os_name, a.arch, a.version).set(1 if _is_online(a.last_checkin) else 0)
        t = telemetry.get(a.id)
        if not t:
            continue
        if t.cpu_usage_percent is not None: CPU_USAGE.labels(*labels).set(t.cpu_usage_percent)
        if t.memory_total_bytes is not None: MEM_TOTAL.labels(*labels).set(t.memory_total_bytes)
        if t.memory_used_bytes is not None: MEM_USED.labels(*labels).set(t.memory_used_bytes)
        if t.memory_usage_percent is not None: MEM_USAGE.labels(*labels).set(t.memory_usage_percent)
        if t.uptime_seconds is not None: UPTIME.labels(*labels).set(t.uptime_seconds)
        if t.process_count is not None: PROCESS_COUNT.labels(*labels).set(t.process_count)
        for disk in t.disks or []:
            mount = str(disk.get("mountpoint", "unknown")); fstype = str(disk.get("fstype", ""))
            dlabels = (*labels, mount, fstype)
            DISK_TOTAL.labels(*dlabels).set(float(disk.get("total_bytes", 0) or 0))
            DISK_USED.labels(*dlabels).set(float(disk.get("used_bytes", 0) or 0))
            DISK_USAGE.labels(*dlabels).set(float(disk.get("usage_percent", 0) or 0))
        for nic in t.interfaces or []:
            name = str(nic.get("name", "unknown")); nlabels = (*labels, name)
            NET_RX.labels(*nlabels).set(float(nic.get("receive_bytes_total", 0) or 0))
            NET_TX.labels(*nlabels).set(float(nic.get("transmit_bytes_total", 0) or 0))

    managed_device_ids = {a.device_id for a in agents}
    for t in db.execute(select(AgentlessTelemetryLatest)).scalars():
        if t.device_id in managed_device_ids:
            continue
        d = db.get(Device, t.device_id)
        if d is None:
            continue
        labels = (d.id, d.hostname or d.ip_address, d.site or "default")
        if t.cpu_usage_percent is not None: CPU_USAGE.labels(*labels).set(t.cpu_usage_percent)
        if t.memory_total_bytes is not None: MEM_TOTAL.labels(*labels).set(t.memory_total_bytes)
        if t.memory_used_bytes is not None: MEM_USED.labels(*labels).set(t.memory_used_bytes)
        if t.memory_usage_percent is not None: MEM_USAGE.labels(*labels).set(t.memory_usage_percent)
        if t.uptime_seconds is not None: UPTIME.labels(*labels).set(t.uptime_seconds)
        if t.process_count is not None: PROCESS_COUNT.labels(*labels).set(t.process_count)
        for disk in t.disks or []:
            mount = str(disk.get("mountpoint", "unknown")); fstype = str(disk.get("fstype", ""))
            dlabels = (*labels, mount, fstype)
            DISK_TOTAL.labels(*dlabels).set(float(disk.get("total_bytes", 0) or 0))
            DISK_USED.labels(*dlabels).set(float(disk.get("used_bytes", 0) or 0))
            DISK_USAGE.labels(*dlabels).set(float(disk.get("usage_percent", 0) or 0))
        for nic in t.interfaces or []:
            name = str(nic.get("name", "unknown")); nlabels = (*labels, name)
            NET_RX.labels(*nlabels).set(float(nic.get("receive_bytes_total", 0) or 0))
            NET_TX.labels(*nlabels).set(float(nic.get("transmit_bytes_total", 0) or 0))


@app.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    _refresh_metric_gauges(db)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/v1/devices", response_model=list[DeviceOut])
def list_devices(
    state: str | None = None,
    device_class: str | None = None,
    site: str | None = None,
    q: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
    identity: dict = Depends(control_identity),
    db: Session = Depends(get_db),
):
    stmt = select(Device).order_by(Device.hostname, Device.ip_address).limit(limit)
    if state: stmt = stmt.where(Device.state == state)
    if device_class: stmt = stmt.where(Device.device_class == device_class)
    if site: stmt = stmt.where(Device.site == site)
    if q:
        stmt = stmt.where((Device.hostname.ilike(f"%{q}%")) | (Device.ip_address.ilike(f"%{q}%")))
    return list(db.execute(stmt).scalars())


@app.post("/api/v1/devices", response_model=DeviceOut, dependencies=[Depends(require_write)])
def create_device(payload: DeviceCreate, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    existing = db.execute(select(Device).where(Device.ip_address == payload.ip_address)).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "device with this IP already exists")
    d = Device(**payload.model_dump())
    db.add(d); db.flush(); add_audit(db, identity["username"], "create", "device", d.id, f"Created device {d.ip_address}"); db.commit(); db.refresh(d)
    return d


@app.get("/api/v1/devices/{device_id}", response_model=DeviceOut)
def get_device(device_id: str, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if not d: raise HTTPException(404, "device not found")
    return d


@app.patch("/api/v1/devices/{device_id}", response_model=DeviceOut, dependencies=[Depends(require_write)])
def patch_device(device_id: str, payload: DevicePatch, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if not d: raise HTTPException(404, "device not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(d, key, value)
    add_audit(db, identity["username"], "update", "device", d.id, f"Updated device {d.hostname or d.ip_address}"); db.commit(); db.refresh(d)
    return d


@app.delete("/api/v1/devices/{device_id}", dependencies=[Depends(require_write)])
def delete_device(device_id: str, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    d = db.get(Device, device_id)
    if not d: raise HTTPException(404, "device not found")
    label = d.hostname or d.ip_address; db.delete(d); add_audit(db, identity["username"], "delete", "device", device_id, f"Deleted device {label}"); db.commit()
    return {"deleted": device_id}


@app.post("/api/v1/discovery/scans", response_model=ScanOut, dependencies=[Depends(require_write)])
def create_scan(payload: ScanCreate, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    try:
        parse_private_network(payload.cidr)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    job = ScanJob(cidr=payload.cidr, site=payload.site)
    db.add(job); db.flush(); add_audit(db, identity["username"], "create", "discovery_scan", job.id, f"Started discovery for {job.cidr}", {"site": job.site}); db.commit(); db.refresh(job)
    return job


@app.get("/api/v1/discovery/scans", response_model=list[ScanOut])
def list_scans(limit: int = Query(100, ge=1, le=500), identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    return list(db.execute(select(ScanJob).order_by(desc(ScanJob.created_at)).limit(limit)).scalars())


@app.get("/api/v1/discovery/scans/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: str, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    job = db.get(ScanJob, scan_id)
    if not job: raise HTTPException(404, "scan not found")
    return job


# ---------------------------- Managed agents v0.3.0 ----------------------------

def _default_policy(db: Session) -> AgentPolicy:
    policy = db.execute(select(AgentPolicy).where(AgentPolicy.is_default.is_(True))).scalar_one_or_none()
    if policy is None:
        raise HTTPException(500, "default agent policy missing")
    return policy


def _agent_from_bearer(authorization: str | None, db: Session) -> ManagedAgent:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing agent credential")
    raw = authorization.split(" ", 1)[1].strip()
    agent = db.execute(select(ManagedAgent).where(ManagedAgent.credential_hash == hash_token(raw))).scalar_one_or_none()
    if agent is None or agent.revoked:
        raise HTTPException(401, "invalid agent credential")
    return agent


@app.get("/api/v1/agent-policies", response_model=list[AgentPolicyOut])
def list_agent_policies(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    return list(db.execute(select(AgentPolicy).order_by(AgentPolicy.name)).scalars())


@app.post("/api/v1/agent-policies", response_model=AgentPolicyOut, dependencies=[Depends(require_write)])
def create_agent_policy(payload: AgentPolicyCreate, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    if db.execute(select(AgentPolicy).where(AgentPolicy.name == payload.name)).scalar_one_or_none():
        raise HTTPException(409, "agent policy name already exists")
    config = payload.model_dump(exclude={"name"})
    policy = AgentPolicy(name=payload.name, config=config, version=1, is_default=False)
    db.add(policy); db.flush(); add_audit(db, identity["username"], "create", "agent_policy", policy.id, f"Created policy {policy.name}"); db.commit(); db.refresh(policy)
    return policy


@app.post("/api/v1/agents/enrollment-tokens", response_model=EnrollmentTokenCreated, dependencies=[Depends(require_write)])
def create_enrollment_token(payload: EnrollmentTokenCreate, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    policy = db.get(AgentPolicy, payload.policy_id) if payload.policy_id else _default_policy(db)
    if policy is None:
        raise HTTPException(404, "agent policy not found")
    raw = new_enrollment_token()
    expires = utcnow() + timedelta(minutes=payload.expires_in_minutes)
    row = AgentEnrollmentToken(
        token_hash=hash_token(raw), token_prefix=raw[:18], policy_id=policy.id, site=payload.site,
        expires_at=expires, max_uses=payload.max_uses,
    )
    db.add(row); db.flush(); add_audit(db, identity["username"], "create", "enrollment_token", row.id, f"Created enrollment token {row.token_prefix}...", {"site": row.site, "max_uses": row.max_uses}); db.commit(); db.refresh(row)
    return EnrollmentTokenCreated(
        id=row.id, token=raw, token_prefix=row.token_prefix, policy_id=row.policy_id,
        site=row.site, expires_at=row.expires_at, max_uses=row.max_uses,
    )


@app.get("/api/v1/agents/enrollment-tokens", response_model=list[EnrollmentTokenOut], dependencies=[Depends(control_identity)])
def list_enrollment_tokens(db: Session = Depends(get_db)):
    return list(db.execute(select(AgentEnrollmentToken).order_by(desc(AgentEnrollmentToken.created_at)).limit(200)).scalars())


@app.delete("/api/v1/agents/enrollment-tokens/{token_id}", dependencies=[Depends(require_write)])
def revoke_enrollment_token(token_id: str, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    row = db.get(AgentEnrollmentToken, token_id)
    if row is None: raise HTTPException(404, "enrollment token not found")
    row.revoked = True; add_audit(db, identity["username"], "revoke", "enrollment_token", row.id, f"Revoked enrollment token {row.token_prefix}..."); db.commit()
    return {"status": "revoked", "id": token_id}


@app.post("/api/v1/agents/enroll", response_model=AgentEnrollResponse)
def enroll_agent(payload: AgentEnrollRequest, request: Request, db: Session = Depends(get_db)):
    token_hash = hash_token(payload.enrollment_token)
    token = db.execute(
        select(AgentEnrollmentToken)
        .where(AgentEnrollmentToken.token_hash == token_hash)
        .with_for_update()
    ).scalar_one_or_none()
    if token is None or token.revoked:
        raise HTTPException(401, "invalid enrollment token")
    expires = token.expires_at if token.expires_at.tzinfo else token.expires_at.replace(tzinfo=timezone.utc)
    if expires <= utcnow():
        raise HTTPException(401, "enrollment token expired")
    if token.used_count >= token.max_uses:
        raise HTTPException(401, "enrollment token exhausted")
    policy = db.get(AgentPolicy, token.policy_id)
    if policy is None:
        raise HTTPException(500, "enrollment policy missing")

    remote = request.client.host if request.client else None
    ip_value = payload.ip_address or remote or f"agent-{new_agent_id()}"
    device = db.execute(select(Device).where(Device.ip_address == ip_value)).scalar_one_or_none()
    if device is None:
        device = Device(ip_address=ip_value, first_seen=utcnow())
        db.add(device); db.flush()
    device.hostname = payload.hostname
    device.os_name = payload.os_name
    device.device_class = "server" if payload.os_name not in {"android", "ios"} else "mobile"
    device.agent_enabled = True
    device.agent_endpoint = "outbound"
    device.agent_version = payload.version
    device.agent_last_seen = utcnow()
    device.last_seen = device.agent_last_seen
    set_device_state(db, device, "up", "agent_enroll")
    device.site = payload.site or token.site or device.site
    device.tags = payload.tags

    raw_credential = new_agent_token()
    agent = db.execute(select(ManagedAgent).where(ManagedAgent.device_id == device.id)).scalar_one_or_none()
    event_type = "agent_reenrolled" if agent else "agent_enrolled"
    if agent is None:
        agent = ManagedAgent(id=new_agent_id(), device_id=device.id, credential_hash=hash_token(raw_credential))
        db.add(agent)
    agent.credential_hash = hash_token(raw_credential)
    agent.hostname = payload.hostname
    agent.os_name = payload.os_name
    agent.arch = payload.arch
    agent.version = payload.version
    agent.policy_id = policy.id
    agent.policy_version = policy.version
    agent.site = device.site
    agent.tags = payload.tags
    agent.last_checkin = utcnow()
    agent.last_ip = ip_value
    agent.revoked = False
    token.used_count += 1
    db.add(Event(device_id=device.id, severity="info", event_type=event_type,
                 message=f"{'Re-enrolled' if event_type == 'agent_reenrolled' else 'Enrolled'} managed agent {payload.hostname}",
                 details={"agent_id": agent.id, "policy": policy.name, "version": payload.version}))
    db.commit(); db.refresh(device); db.refresh(agent)
    return AgentEnrollResponse(
        agent_id=agent.id, device_id=device.id, agent_token=raw_credential,
        policy_id=policy.id, policy_version=policy.version, policy=policy.config,
    )


@app.post("/api/v1/agents/checkin", response_model=AgentCheckinResponse)
def managed_agent_checkin(
    payload: AgentCheckinRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent = _agent_from_bearer(authorization, db)
    now = utcnow()
    if payload.hostname: agent.hostname = payload.hostname
    if payload.version: agent.version = payload.version
    remote = request.client.host if request.client else None
    agent.last_ip = payload.ip_address or remote or agent.last_ip
    agent.last_checkin = now
    policy = db.get(AgentPolicy, agent.policy_id)
    if policy is None: raise HTTPException(500, "agent policy missing")
    agent.policy_version = policy.version
    device = db.get(Device, agent.device_id)
    if device:
        device.hostname = agent.hostname; device.agent_version = agent.version
        device.agent_last_seen = now; device.last_seen = now; set_device_state(db, device, "up", "agent_checkin")
        if payload.ip_address and device.ip_address != payload.ip_address:
            collision = db.execute(select(Device).where(Device.ip_address == payload.ip_address, Device.id != device.id)).scalar_one_or_none()
            if collision is None: device.ip_address = payload.ip_address
    db.commit()
    return AgentCheckinResponse(status="ok", policy_id=policy.id, policy_version=policy.version,
                                policy=policy.config, server_time=now)


@app.post("/api/v1/agents/telemetry")
def managed_agent_telemetry(
    payload: AgentTelemetryIn,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    agent = _agent_from_bearer(authorization, db)
    now = utcnow(); agent.last_checkin = now
    row = db.get(AgentTelemetryLatest, agent.id)
    values = payload.model_dump()
    values["disks"] = [d.model_dump() for d in payload.disks]
    values["interfaces"] = [i.model_dump() for i in payload.interfaces]
    if row is None:
        row = AgentTelemetryLatest(agent_id=agent.id, **values)
        db.add(row)
    else:
        for key, value in values.items(): setattr(row, key, value)
    device = db.get(Device, agent.device_id)
    if device:
        device.agent_last_seen = now; device.last_seen = now; set_device_state(db, device, "up", "agent_telemetry"); device.agent_version = agent.version
    db.commit()
    sync_problems(db)
    return {"status": "accepted", "agent_id": agent.id}


@app.get("/api/v1/agents", response_model=list[ManagedAgentOut])
def list_managed_agents(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    agents = list(db.execute(select(ManagedAgent).order_by(ManagedAgent.hostname)).scalars())
    return [ManagedAgentOut(
        id=a.id, device_id=a.device_id, hostname=a.hostname, os_name=a.os_name, arch=a.arch,
        version=a.version, policy_id=a.policy_id, policy_version=a.policy_version, site=a.site,
        tags=a.tags or [], enrolled_at=a.enrolled_at, last_checkin=a.last_checkin, last_ip=a.last_ip,
        revoked=a.revoked, online=(not a.revoked and _is_online(a.last_checkin)),
    ) for a in agents]


@app.post("/api/v1/agents/{agent_id}/revoke", dependencies=[Depends(require_write)])
def revoke_agent(agent_id: str, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    agent = db.get(ManagedAgent, agent_id)
    if not agent: raise HTTPException(404, "agent not found")
    agent.revoked = True
    device = db.get(Device, agent.device_id)
    if device: set_device_state(db, device, "down", "agent_revoked")
    add_audit(db, identity["username"], "revoke", "agent", agent.id, f"Revoked agent {agent.hostname}")
    db.commit()
    return {"status": "revoked", "agent_id": agent_id}


# v0.2.2 pull-agent endpoints remain for backwards compatibility only.
@app.post("/api/v1/agents/register", response_model=AgentRegisterResponse, dependencies=[Depends(require_write)], include_in_schema=False)
def register_agent_legacy(payload: AgentRegister, request: Request, db: Session = Depends(get_db)):
    now = utcnow(); device = db.get(Device, payload.device_id) if payload.device_id else None
    remote = request.client.host if request.client else None
    endpoint = payload.advertise_address or (f"{remote}:9123" if remote else None)
    ip_value = remote or (endpoint.split(":", 1)[0] if endpoint else payload.hostname)
    if device is None: device = db.execute(select(Device).where(Device.ip_address == ip_value)).scalar_one_or_none()
    if device is None: device = Device(ip_address=ip_value, first_seen=now); db.add(device)
    device.hostname = payload.hostname; device.os_name = payload.os_name; device.device_class = "server"
    device.agent_enabled = True; device.agent_endpoint = endpoint; device.agent_version = payload.version
    device.agent_last_seen = now; device.last_seen = now; set_device_state(db, device, "up", "legacy_agent_register"); device.site = payload.site; device.tags = payload.tags
    db.commit(); db.refresh(device)
    return AgentRegisterResponse(device_id=device.id, scrape_endpoint=device.agent_endpoint or "")


@app.post("/api/v1/agents/heartbeat", dependencies=[Depends(require_write)], include_in_schema=False)
def heartbeat_legacy(payload: Heartbeat, db: Session = Depends(get_db)):
    d = db.get(Device, payload.device_id)
    if not d: raise HTTPException(404, "device not found")
    d.agent_last_seen = utcnow(); d.last_seen = d.agent_last_seen; set_device_state(db, d, "up", "legacy_agent_heartbeat")
    if payload.version: d.agent_version = payload.version
    db.commit(); return {"status": "ok"}


# ---------------------------- Installers/artifacts -----------------------------
WINDOWS_INSTALLER = r'''param(
  [Parameter(Mandatory=$true)][string]$Server,
  [Parameter(Mandatory=$true)][string]$Token,
  [string]$Site = "default",
  [string]$Tags = ""
)
$ErrorActionPreference = "Stop"
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host "Requesting Administrator privileges..."
  $elevateArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Server',('"'+$Server+'"'),'-Token',('"'+$Token+'"'),'-Site',('"'+$Site+'"'))
if (-not [string]::IsNullOrWhiteSpace($Tags)) {
  $elevateArgs += @('-Tags', ('"'+$Tags+'"'))
}
  Start-Process powershell.exe -Verb RunAs -ArgumentList $elevateArgs
  exit
}
$Server = $Server.TrimEnd('/')
$tmp = Join-Path $env:TEMP "sentinel-agent.exe"
$sumFile = Join-Path $env:TEMP "sentinel-agent.exe.sha256"
Write-Host "Downloading SentinelView Agent..."
Invoke-WebRequest -UseBasicParsing "$Server/downloads/agents/sentinel-agent-windows-amd64.exe" -OutFile $tmp
Invoke-WebRequest -UseBasicParsing "$Server/downloads/agents/sentinel-agent-windows-amd64.exe.sha256" -OutFile $sumFile
$expected = ((Get-Content $sumFile -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$actual = (Get-FileHash -Algorithm SHA256 $tmp).Hash.ToLowerInvariant()
if ($expected -ne $actual) { throw "Agent SHA-256 verification failed" }
Write-Host "SHA-256 verified. Installing and enrolling agent..."
$installArgs = @('install','--server',$Server,'--token',$Token,'--site',$Site)
if (-not [string]::IsNullOrWhiteSpace($Tags)) {
  $installArgs += @('--tags', $Tags)
}
& $tmp @installArgs
if ($LASTEXITCODE -ne 0) { throw "SentinelView Agent installation failed with exit code $LASTEXITCODE" }
$configPath = Join-Path $env:ProgramData "SentinelView\agent.json"
if (Test-Path $configPath) {
  & icacls.exe $configPath /inheritance:r /grant:r "*S-1-5-18:F" "*S-1-5-32-544:F" /q | Out-Null
}
Remove-Item $tmp -Force -ErrorAction SilentlyContinue
Remove-Item $sumFile -Force -ErrorAction SilentlyContinue
Write-Host "SentinelView Agent installed successfully."
'''

LINUX_INSTALLER = r'''#!/bin/sh
set -eu
SERVER=""; TOKEN=""; SITE="default"; TAGS=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --server) SERVER="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --site) SITE="$2"; shift 2 ;;
    --tags) TAGS="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$SERVER" ] && [ -n "$TOKEN" ] || { echo "--server and --token are required" >&2; exit 2; }
if [ "$(id -u)" -ne 0 ]; then echo "Run through sudo (the UI command already does this)." >&2; exit 1; fi
ARCH=$(uname -m)
case "$ARCH" in x86_64|amd64) ART="sentinel-agent-linux-amd64" ;; *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;; esac
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
curl -fsSL "${SERVER%/}/downloads/agents/$ART" -o "$TMP"
EXPECTED=$(curl -fsSL "${SERVER%/}/downloads/agents/$ART.sha256" | awk '{print $1}')
ACTUAL=$(sha256sum "$TMP" | awk '{print $1}')
[ "$EXPECTED" = "$ACTUAL" ] || { echo "Agent SHA-256 verification failed" >&2; exit 1; }
chmod +x "$TMP"
"$TMP" install --server "${SERVER%/}" --token "$TOKEN" --site "$SITE" --tags "$TAGS"
echo "SentinelView Agent installed successfully."
'''


@app.get("/install/windows.ps1", response_class=PlainTextResponse)
def windows_installer():
    return WINDOWS_INSTALLER


@app.get("/install/linux.sh", response_class=PlainTextResponse)
def linux_installer():
    return LINUX_INSTALLER


@app.get("/downloads/agents/{filename}")
def download_agent(filename: str):
    allowed = {
        "sentinel-agent-windows-amd64.exe",
        "sentinel-agent-windows-amd64.exe.sha256",
        "sentinel-agent-linux-amd64",
        "sentinel-agent-linux-amd64.sha256",
    }
    if filename not in allowed: raise HTTPException(404, "artifact not found")
    path = Path(settings.artifact_dir) / filename
    if not path.is_file():
        raise HTTPException(503, "agent artifact is not present in this build")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


# ----------------------------- Existing integrations ---------------------------
@app.get("/api/v1/targets/prometheus")
def prometheus_targets(db: Session = Depends(get_db)):
    # Legacy pull targets only. Managed v0.3.0 agents push telemetry to control-api.
    out = []
    for d in db.execute(select(Device).where(Device.agent_enabled.is_(True), Device.agent_endpoint != "outbound")).scalars():
        if not d.agent_endpoint: continue
        out.append({"targets": [d.agent_endpoint], "labels": {"host_id": d.id, "hostname": d.hostname or d.ip_address,
                    "site": d.site or "default", "device_class": d.device_class}})
    return out


@app.get("/api/v1/targets/snmp")
def snmp_targets(db: Session = Depends(get_db)):
    out = []
    for d in db.execute(select(Device).where(Device.snmp_enabled.is_(True))).scalars():
        out.append({"targets": [d.ip_address], "labels": {"host_id": d.id, "hostname": d.hostname or d.ip_address,
                    "site": d.site or "default", "device_class": d.device_class,
                    "snmp_module": d.snmp_module, "snmp_auth": d.snmp_auth}})
    return out


@app.get("/api/v1/targets/blackbox")
def blackbox_targets(db: Session = Depends(get_db)):
    return [{"targets": [d.ip_address], "labels": {"host_id": d.id, "hostname": d.hostname or d.ip_address,
            "site": d.site or "default"}} for d in db.execute(select(Device)).scalars()]


@app.get("/api/v1/rules", response_model=list[AlertRuleOut])
def list_rules(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    return list(db.execute(select(AlertRule).order_by(AlertRule.name)).scalars())


@app.post("/api/v1/rules", response_model=AlertRuleOut, dependencies=[Depends(require_write)])
def create_rule(payload: AlertRuleCreate, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    rule = AlertRule(**payload.model_dump()); db.add(rule); db.flush(); add_audit(db, identity["username"], "create", "rule", rule.id, f"Created monitoring rule {rule.name}"); db.commit(); db.refresh(rule); return rule


@app.get("/api/v1/events", response_model=list[EventOut])
def list_events(limit: int = Query(200, ge=1, le=2000), identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    return list(db.execute(select(Event).order_by(desc(Event.created_at)).limit(limit)).scalars())


@app.get("/api/v1/topology", response_model=list[EdgeOut])
def list_topology(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    return list(db.execute(select(TopologyEdge).order_by(TopologyEdge.created_at)).scalars())


@app.post("/api/v1/topology", response_model=EdgeOut, dependencies=[Depends(require_write)])
def create_edge(payload: EdgeCreate, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    if not db.get(Device, payload.source_device_id) or not db.get(Device, payload.target_device_id):
        raise HTTPException(400, "source and target devices must exist")
    edge = TopologyEdge(**payload.model_dump()); db.add(edge); db.flush(); add_audit(db, identity["username"], "create", "topology_edge", edge.id, f"Created topology edge {edge.relation}"); db.commit(); db.refresh(edge); return edge


# ----------------------- v0.3.0 first-party operations UI ----------------------

def _managed_agent_for_device(db: Session, device_id: str) -> ManagedAgent | None:
    return db.execute(select(ManagedAgent).where(ManagedAgent.device_id == device_id)).scalar_one_or_none()


def _managed_agent_out(agent: ManagedAgent | None) -> ManagedAgentOut | None:
    if agent is None:
        return None
    return ManagedAgentOut(
        id=agent.id, device_id=agent.device_id, hostname=agent.hostname, os_name=agent.os_name,
        arch=agent.arch, version=agent.version, policy_id=agent.policy_id, policy_version=agent.policy_version,
        site=agent.site, tags=agent.tags or [], enrolled_at=agent.enrolled_at, last_checkin=agent.last_checkin,
        last_ip=agent.last_ip, revoked=agent.revoked, online=(not agent.revoked and _is_online(agent.last_checkin)),
    )


def _telemetry_dict(row: AgentTelemetryLatest | None) -> dict | None:
    if row is None:
        return None
    return {
        "source": getattr(row, "source", "agent"),
        "collected_at": row.collected_at,
        "cpu_usage_percent": row.cpu_usage_percent,
        "memory_total_bytes": row.memory_total_bytes,
        "memory_used_bytes": row.memory_used_bytes,
        "memory_usage_percent": row.memory_usage_percent,
        "uptime_seconds": row.uptime_seconds,
        "process_count": row.process_count,
        "disks": row.disks or [],
        "interfaces": row.interfaces or [],
    }


def _host_summary(db: Session, device: Device, problems: list[Problem] | None = None) -> HostSummaryOut:
    agent = _managed_agent_for_device(db, device.id)
    services = services_for_device(db, device)
    if problems is None:
        problems = list(db.execute(select(Problem).where(Problem.device_id == device.id, Problem.state != "resolved")).scalars())
    return HostSummaryOut(
        id=device.id, hostname=device.hostname, ip_address=device.ip_address, state=device.state,
        device_class=device.device_class, os_name=device.os_name, site=device.site,
        agent_enabled=bool(agent and not agent.revoked), agent_online=is_agent_online(agent),
        agent_version=(agent.version if agent else None),
        problem_count=len(problems), critical_count=sum(1 for p in problems if p.severity == "critical"),
        warning_count=sum(1 for p in problems if p.severity == "warning"), service_count=len(services),
        last_seen=device.last_seen,
    )


@app.get("/api/v1/ui/overview")
def ui_overview(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    problems = [p for p in sync_problems(db) if p.state != "resolved"]
    devices = list(db.execute(select(Device)).scalars())
    agents = list(db.execute(select(ManagedAgent).where(ManagedAgent.revoked.is_(False))).scalars())
    services = all_services(db)
    site_counts: dict[str, dict] = {}
    for d in devices:
        site = d.site or "default"
        bucket = site_counts.setdefault(site, {"site": site, "total": 0, "up": 0, "down": 0, "problems": 0})
        bucket["total"] += 1
        if d.state == "up": bucket["up"] += 1
        elif d.state == "down": bucket["down"] += 1
    for p in problems:
        d = db.get(Device, p.device_id)
        if d:
            site_counts.setdefault(d.site or "default", {"site": d.site or "default", "total": 0, "up": 0, "down": 0, "problems": 0})["problems"] += 1
    return {
        "version": "0.3.0",
        "hosts": {"total": len(devices), "up": sum(1 for d in devices if d.state == "up"), "down": sum(1 for d in devices if d.state == "down"), "unknown": sum(1 for d in devices if d.state not in {"up", "down"})},
        "services": {"total": len(services), "ok": sum(1 for s in services if s["state"] == "ok"), "warning": sum(1 for s in services if s["state"] == "warning"), "critical": sum(1 for s in services if s["state"] == "critical"), "unknown": sum(1 for s in services if s["state"] == "unknown")},
        "problems": {"total": len(problems), "critical": sum(1 for p in problems if p.severity == "critical"), "warning": sum(1 for p in problems if p.severity == "warning"), "acknowledged": sum(1 for p in problems if p.state == "acknowledged")},
        "agents": {"total": len(agents), "online": sum(1 for a in agents if is_agent_online(a)), "offline": sum(1 for a in agents if not is_agent_online(a))},
        "sites": sorted(site_counts.values(), key=lambda x: x["site"]),
        "recent_problems": [ProblemOut.model_validate(p).model_dump(mode="json") for p in problems[:8]],
        "recent_events": [EventOut.model_validate(e).model_dump(mode="json") for e in db.execute(select(Event).order_by(desc(Event.created_at)).limit(10)).scalars()],
    }


@app.get("/api/v1/hosts", response_model=list[HostSummaryOut])
def list_hosts(
    state: str | None = None, site: str | None = None, q: str | None = None,
    identity: dict = Depends(control_identity), db: Session = Depends(get_db),
):
    sync_problems(db)
    stmt = select(Device).order_by(Device.hostname, Device.ip_address)
    if state: stmt = stmt.where(Device.state == state)
    if site: stmt = stmt.where(Device.site == site)
    if q: stmt = stmt.where((Device.hostname.ilike(f"%{q}%")) | (Device.ip_address.ilike(f"%{q}%")))
    all_open = list(db.execute(select(Problem).where(Problem.state != "resolved")).scalars())
    by_device: dict[str, list[Problem]] = {}
    for problem in all_open: by_device.setdefault(problem.device_id, []).append(problem)
    return [_host_summary(db, d, by_device.get(d.id, [])) for d in db.execute(stmt).scalars()]


@app.get("/api/v1/hosts/{device_id}/overview", response_model=HostOverviewOut)
def host_overview(device_id: str, identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None: raise HTTPException(404, "host not found")
    sync_problems(db)
    agent = _managed_agent_for_device(db, device.id)
    telemetry, _telemetry_source = latest_telemetry_for_device(db, device)
    problems = list(db.execute(select(Problem).where(Problem.device_id == device.id, Problem.state != "resolved").order_by(desc(Problem.opened_at))).scalars())
    return HostOverviewOut(
        device=DeviceOut.model_validate(device), agent=_managed_agent_out(agent), telemetry=_telemetry_dict(telemetry),
        services=[ServiceOut(**s) for s in services_for_device(db, device)],
        problems=[ProblemOut.model_validate(p) for p in problems],
    )


@app.get("/api/v1/services", response_model=list[ServiceOut])
def list_services(
    host_id: str | None = None, state: str | None = None, q: str | None = None,
    identity: dict = Depends(control_identity), db: Session = Depends(get_db),
):
    if host_id:
        device = db.get(Device, host_id)
        if device is None: raise HTTPException(404, "host not found")
        rows = services_for_device(db, device)
    else:
        rows = all_services(db)
    if state: rows = [row for row in rows if row["state"] == state]
    if q:
        needle = q.lower()
        rows = [row for row in rows if needle in f"{row['hostname']} {row['service_name']} {row['message']}".lower()]
    return [ServiceOut(**row) for row in rows]


@app.get("/api/v1/problems", response_model=list[ProblemOut])
def list_problems(
    state: str | None = "active", severity: str | None = None, device_id: str | None = None,
    identity: dict = Depends(control_identity), db: Session = Depends(get_db),
):
    sync_problems(db)
    stmt = select(Problem).order_by(desc(Problem.opened_at))
    if state == "active": stmt = stmt.where(Problem.state != "resolved")
    elif state: stmt = stmt.where(Problem.state == state)
    if severity: stmt = stmt.where(Problem.severity == severity)
    if device_id: stmt = stmt.where(Problem.device_id == device_id)
    return list(db.execute(stmt).scalars())


@app.post("/api/v1/problems/{problem_id}/ack", response_model=ProblemOut)
def acknowledge_problem(problem_id: str, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    problem = db.get(Problem, problem_id)
    if problem is None: raise HTTPException(404, "problem not found")
    if problem.state == "resolved": raise HTTPException(409, "problem is already resolved")
    problem.state = "acknowledged"; problem.acknowledged_at = utcnow(); problem.acknowledged_by = identity["username"]
    add_audit(db, identity["username"], "acknowledge", "problem", problem.id, f"Acknowledged {problem.title}")
    db.commit(); db.refresh(problem)
    return problem


@app.get("/api/v1/hosts/{device_id}/metrics")
def host_metric_history(
    device_id: str, metric: str = Query("cpu", pattern="^(cpu|memory|disk|processes)$"),
    range: str = Query("1h", pattern="^(15m|1h|6h|24h|7d)$"), step: int = Query(60, ge=15, le=3600),
    identity: dict = Depends(control_identity), db: Session = Depends(get_db),
):
    device = db.get(Device, device_id)
    if device is None: raise HTTPException(404, "host not found")
    metric_names = {
        "cpu": "sentinel_cpu_usage_percent",
        "memory": "sentinel_memory_usage_percent",
        "disk": "sentinel_disk_usage_percent",
        "processes": "sentinel_process_count",
    }
    seconds = {"15m": 900, "1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}[range]
    end = utcnow().timestamp(); start = end - seconds
    query = f'{metric_names[metric]}{{host_id="{device.id}"}}'
    try:
        response = httpx.get(
            f"{settings.prometheus_url.rstrip('/')}/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": step}, timeout=4.0,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success": raise RuntimeError("Prometheus query failed")
        return {"available": True, "metric": metric, "range": range, "series": payload.get("data", {}).get("result", [])}
    except Exception as exc:
        logger.debug("Prometheus history unavailable: %s", exc)
        return {"available": False, "metric": metric, "range": range, "series": [], "error": "Prometheus history unavailable"}


@app.get("/api/v1/search")
def global_search(q: str = Query(min_length=1, max_length=160), identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    devices = list(db.execute(select(Device).where((Device.hostname.ilike(f"%{q}%")) | (Device.ip_address.ilike(f"%{q}%"))).limit(10)).scalars())
    events = list(db.execute(select(Event).where(Event.message.ilike(f"%{q}%")).order_by(desc(Event.created_at)).limit(10)).scalars())
    return {
        "hosts": [{"id": d.id, "title": d.hostname or d.ip_address, "subtitle": f"{d.ip_address} · {d.device_class} · {d.state}"} for d in devices],
        "events": [{"id": e.id, "title": e.message, "subtitle": f"{e.event_type} · {e.severity}", "device_id": e.device_id} for e in events],
    }


@app.patch("/api/v1/agent-policies/{policy_id}", response_model=AgentPolicyOut)
def patch_agent_policy(policy_id: str, payload: PolicyPatch, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    policy = db.get(AgentPolicy, policy_id)
    if policy is None: raise HTTPException(404, "policy not found")
    config = dict(policy.config or {})
    config.update(payload.model_dump(exclude_unset=True))
    policy.config = config; policy.version += 1; policy.updated_at = utcnow()
    add_audit(db, identity["username"], "update", "agent_policy", policy.id, f"Updated policy {policy.name}", {"version": policy.version})
    db.commit(); db.refresh(policy)
    return policy


@app.patch("/api/v1/rules/{rule_id}", response_model=AlertRuleOut)
def patch_rule(rule_id: str, payload: RulePatch, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    rule = db.get(AlertRule, rule_id)
    if rule is None: raise HTTPException(404, "rule not found")
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(rule, key, value)
    add_audit(db, identity["username"], "update", "rule", rule.id, f"Updated monitoring rule {rule.name}")
    db.commit(); db.refresh(rule); sync_problems(db)
    return rule


@app.delete("/api/v1/rules/{rule_id}")
def delete_rule(rule_id: str, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    rule = db.get(AlertRule, rule_id)
    if rule is None: raise HTTPException(404, "rule not found")
    name = rule.name; db.delete(rule)
    add_audit(db, identity["username"], "delete", "rule", rule_id, f"Deleted monitoring rule {name}")
    db.commit(); return {"deleted": rule_id}


@app.get("/api/v1/topology/graph", response_model=TopologyGraphOut)
def topology_graph(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    devices = list(db.execute(select(Device)).scalars())
    problems = list(db.execute(select(Problem).where(Problem.state != "resolved")).scalars())
    severity_by_device: dict[str, str] = {}
    for p in problems:
        if p.severity == "critical" or p.device_id not in severity_by_device: severity_by_device[p.device_id] = p.severity
    nodes = [{"id": d.id, "label": d.hostname or d.ip_address, "ip": d.ip_address, "state": d.state, "device_class": d.device_class, "site": d.site, "severity": severity_by_device.get(d.id)} for d in devices]
    edges = [{"id": e.id, "source": e.source_device_id, "target": e.target_device_id, "relation": e.relation, "metadata": e.metadata_json} for e in db.execute(select(TopologyEdge)).scalars()]
    return TopologyGraphOut(nodes=nodes, edges=edges)


@app.get("/api/v1/integrations")
def list_integrations(identity: dict = Depends(control_identity)):
    return [
        {"id": "windows", "name": "Windows", "category": "Operating system", "status": "available", "features": ["agent", "inventory", "metrics", "alerts"]},
        {"id": "linux", "name": "Linux", "category": "Operating system", "status": "available", "features": ["agent", "inventory", "metrics", "alerts"]},
        {"id": "snmp", "name": "Generic SNMP", "category": "Network", "status": "available", "features": ["discovery", "metrics", "inventory"]},
        {"id": "blackbox", "name": "HTTP/TCP/ICMP", "category": "Synthetic", "status": "available", "features": ["availability", "latency"]},
        {"id": "apc", "name": "APC UPS", "category": "Power", "status": "planned", "features": ["snmp", "battery", "load", "runtime"]},
        {"id": "vertiv", "name": "Vertiv", "category": "Environmental", "status": "planned", "features": ["snmp", "temperature", "cooling"]},
        {"id": "docker", "name": "Docker", "category": "Container", "status": "planned", "features": ["metrics", "inventory"]},
        {"id": "proxmox", "name": "Proxmox", "category": "Virtualization", "status": "planned", "features": ["api", "inventory", "metrics"]},
    ]


@app.get("/api/v1/notification-channels", response_model=list[NotificationChannelOut])
def list_notification_channels(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    return list(db.execute(select(NotificationChannel).order_by(NotificationChannel.name)).scalars())


@app.post("/api/v1/notification-channels", response_model=NotificationChannelOut)
def create_notification_channel(payload: NotificationChannelCreate, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    if db.execute(select(NotificationChannel).where(NotificationChannel.name == payload.name)).scalar_one_or_none():
        raise HTTPException(409, "notification channel name already exists")
    row = NotificationChannel(**payload.model_dump()); db.add(row); db.flush()
    add_audit(db, identity["username"], "create", "notification_channel", row.id, f"Created channel {row.name}", {"type": row.channel_type})
    db.commit(); db.refresh(row); return row


@app.delete("/api/v1/notification-channels/{channel_id}")
def delete_notification_channel(channel_id: str, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    row = db.get(NotificationChannel, channel_id)
    if row is None: raise HTTPException(404, "notification channel not found")
    name = row.name; db.delete(row); add_audit(db, identity["username"], "delete", "notification_channel", channel_id, f"Deleted channel {name}")
    db.commit(); return {"deleted": channel_id}


@app.get("/api/v1/maintenance", response_model=list[MaintenanceOut])
def list_maintenance(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    return list(db.execute(select(MaintenanceWindow).order_by(desc(MaintenanceWindow.starts_at))).scalars())


@app.post("/api/v1/maintenance", response_model=MaintenanceOut)
def create_maintenance(payload: MaintenanceCreate, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    if payload.ends_at <= payload.starts_at: raise HTTPException(400, "ends_at must be after starts_at")
    row = MaintenanceWindow(**payload.model_dump(), created_by=identity["username"]); db.add(row); db.flush()
    add_audit(db, identity["username"], "create", "maintenance", row.id, f"Created maintenance {row.name}")
    db.commit(); db.refresh(row); return row


@app.delete("/api/v1/maintenance/{window_id}")
def delete_maintenance(window_id: str, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    row = db.get(MaintenanceWindow, window_id)
    if row is None: raise HTTPException(404, "maintenance window not found")
    name = row.name; db.delete(row); add_audit(db, identity["username"], "delete", "maintenance", window_id, f"Deleted maintenance {name}")
    db.commit(); return {"deleted": window_id}


@app.get("/api/v1/slas", response_model=list[SlaOut])
def list_slas(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    return list(db.execute(select(SlaDefinition).order_by(SlaDefinition.name)).scalars())


@app.post("/api/v1/slas", response_model=SlaOut)
def create_sla(payload: SlaCreate, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    row = SlaDefinition(**payload.model_dump()); db.add(row); db.flush()
    add_audit(db, identity["username"], "create", "sla", row.id, f"Created SLA {row.name}", {"target": row.target_percent})
    db.commit(); db.refresh(row); return row


def _availability_for_device(db: Session, device: Device, hours: int) -> float:
    end = utcnow(); start = end - timedelta(hours=hours)
    events = list(db.execute(
        select(Event).where(Event.device_id == device.id, Event.event_type == "state_change", Event.created_at >= start).order_by(Event.created_at)
    ).scalars())
    if not events:
        return 100.0 if device.state == "up" else 0.0
    first = events[0]
    state = (first.details or {}).get("from", "unknown")
    cursor = start
    up_seconds = 0.0
    for event in events:
        at = event.created_at if event.created_at.tzinfo else event.created_at.replace(tzinfo=timezone.utc)
        at = max(start, min(at, end))
        if state == "up": up_seconds += max(0.0, (at - cursor).total_seconds())
        state = (event.details or {}).get("to", state)
        cursor = at
    if state == "up": up_seconds += max(0.0, (end - cursor).total_seconds())
    return round(100.0 * up_seconds / max(1.0, (end - start).total_seconds()), 4)


@app.get("/api/v1/availability")
def availability(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    rows = []
    for d in db.execute(select(Device).order_by(Device.hostname, Device.ip_address)).scalars():
        rows.append({
            "device_id": d.id, "hostname": d.hostname or d.ip_address, "ip_address": d.ip_address, "site": d.site,
            "state": d.state, "availability_24h": _availability_for_device(db, d, 24),
            "availability_7d": _availability_for_device(db, d, 24 * 7),
            "availability_30d": _availability_for_device(db, d, 24 * 30),
        })
    slas = []
    for sla in db.execute(select(SlaDefinition).where(SlaDefinition.enabled.is_(True))).scalars():
        targets = [r for r in rows if (sla.device_id is None or r["device_id"] == sla.device_id) and (sla.site is None or r["site"] == sla.site)]
        current = round(sum(r["availability_30d"] for r in targets) / len(targets), 4) if targets else None
        slas.append({"id": sla.id, "name": sla.name, "target_percent": sla.target_percent, "current_percent": current, "status": "pass" if current is not None and current >= sla.target_percent else "fail" if current is not None else "unknown"})
    return {"hosts": rows, "slas": slas, "history_note": "Availability history becomes authoritative from v0.3.0 state-change events onward."}


@app.get("/api/v1/audit", response_model=list[AuditOut])
def list_audit(limit: int = Query(300, ge=1, le=2000), identity: dict = Depends(require_roles("admin", "operator")), db: Session = Depends(get_db)):
    return list(db.execute(select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(limit)).scalars())


@app.get("/api/v1/platform/settings")
def platform_settings(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    return {
        "version": "0.3.0",
        "monitoring_ui": "SentinelView",
        "prometheus_url": settings.prometheus_url,
        "agent_online_seconds": settings.agent_online_seconds,
        "scan_max_hosts": settings.scan_max_hosts,
        "authentication": "local session + API key compatibility",
        "features": {
            "first_party_ui": True, "managed_agents": True, "discovery": True, "problems": True,
            "services": True, "rules": True, "topology": True, "maintenance": True, "availability": True,
            "local_rbac": True, "grafana_optional_ui": True,
        },
    }
