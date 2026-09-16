from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .maintenance_engine import notifications_suppressed
from .models import AgentlessMonitor, AgentlessTelemetryLatest, AgentTelemetryLatest, AlertRule, Device, Event, ManagedAgent, Problem
from .notification_engine import enqueue_problem_transition


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_agent_online(agent: ManagedAgent | None) -> bool:
    if agent is None or agent.revoked or agent.last_checkin is None:
        return False
    seen = _aware(agent.last_checkin)
    return bool(seen and (utcnow() - seen).total_seconds() <= settings.agent_online_seconds)


def remote_monitor_health(monitor: AgentlessMonitor, now: datetime | None = None) -> str:
    now = now or utcnow()
    if not monitor.enabled:
        return "unknown"
    if int(monitor.consecutive_failures or 0) >= 3:
        return "down"
    success = _aware(monitor.last_success_at)
    if success is None:
        return "unknown"
    max_age = max(120, int(monitor.interval_seconds or 60) * 3)
    if (now - success).total_seconds() > max_age:
        return "unknown"
    return "up"


def monitoring_method_states(db: Session, device: Device, now: datetime | None = None) -> list[tuple[str, str]]:
    now = now or utcnow()
    states: list[tuple[str, str]] = []
    agent = db.execute(
        select(ManagedAgent).where(
            ManagedAgent.device_id == device.id,
            ManagedAgent.revoked.is_(False),
        )
    ).scalar_one_or_none()
    if agent is not None:
        states.append(("agent", "up" if is_agent_online(agent) else "down"))

    monitors = list(
        db.execute(
            select(AgentlessMonitor).where(
                AgentlessMonitor.device_id == device.id,
                AgentlessMonitor.enabled.is_(True),
            )
        ).scalars()
    )
    states.extend((monitor.method, remote_monitor_health(monitor, now)) for monitor in monitors)
    return states


def derive_device_health(db: Session, device: Device, now: datetime | None = None) -> str:
    states = [state for _method, state in monitoring_method_states(db, device, now)]
    if not states or all(state == "unknown" for state in states):
        return "unknown"
    has_up = "up" in states
    has_down = "down" in states
    if has_up and has_down:
        return "degraded"
    if has_up:
        return "up"
    if has_down:
        return "down"
    return "unknown"


def reconcile_device_health(db: Session, device: Device, now: datetime | None = None) -> str:
    now = now or utcnow()
    target = derive_device_health(db, device, now)
    previous = device.state or "unknown"
    if previous == target:
        return target
    device.state = target
    db.add(
        Event(
            device_id=device.id,
            severity="critical" if target == "down" else "warning" if target == "degraded" else "info",
            event_type="state_change",
            message=f"{device.hostname or device.ip_address}: {previous} -> {target}",
            details={
                "from": previous,
                "to": target,
                "source": "monitoring_aggregate",
                "methods": [
                    {"method": method, "state": state}
                    for method, state in monitoring_method_states(db, device, now)
                ],
            },
        )
    )
    return target


def compare(value: float, operator: str, threshold: float | None) -> bool:
    if threshold is None:
        return False
    if operator == ">": return value > threshold
    if operator == ">=": return value >= threshold
    if operator == "<": return value < threshold
    if operator == "<=": return value <= threshold
    if operator in {"=", "=="}: return value == threshold
    return False


def state_from_rule(value: float | None, rule: AlertRule | None) -> tuple[str, float | None]:
    if value is None:
        return "unknown", None
    if rule is None or not rule.enabled:
        return "ok", None
    if compare(value, rule.operator, rule.critical_threshold):
        return "critical", rule.critical_threshold
    if compare(value, rule.operator, rule.warning_threshold):
        return "warning", rule.warning_threshold
    return "ok", None


def _rule_map(db: Session) -> dict[str, AlertRule]:
    rules = list(
        db.execute(
            select(AlertRule)
            .where(AlertRule.enabled.is_(True))
            .order_by(AlertRule.created_at, AlertRule.id)
        ).scalars()
    )
    return {rule.metric: rule for rule in rules}


def latest_telemetry_for_device(db: Session, device: Device):
    agent = db.execute(
        select(ManagedAgent).where(
            ManagedAgent.device_id == device.id,
            ManagedAgent.revoked.is_(False),
        )
    ).scalar_one_or_none()
    if agent is not None:
        row = db.get(AgentTelemetryLatest, agent.id)
        if row is not None:
            return row, "agent"
    row = db.get(AgentlessTelemetryLatest, device.id)
    if row is not None:
        return row, row.source
    return None, None


def services_for_device(db: Session, device: Device) -> list[dict]:
    rules = _rule_map(db)
    now = utcnow()
    agent = db.execute(
        select(ManagedAgent).where(
            ManagedAgent.device_id == device.id,
            ManagedAgent.revoked.is_(False),
        )
    ).scalar_one_or_none()
    telemetry, telemetry_source = latest_telemetry_for_device(db, device)
    hostname = device.hostname or device.ip_address
    updated = telemetry.collected_at if telemetry else device.last_seen
    services: list[dict] = []

    asset_health = derive_device_health(db, device, now)
    host_state = "ok" if asset_health == "up" else "warning" if asset_health == "degraded" else "critical" if asset_health == "down" else "unknown"
    services.append({
        "host_id": device.id,
        "hostname": hostname,
        "service_key": "host:availability",
        "service_name": "Asset health",
        "state": host_state,
        "value": 1 if asset_health == "up" else 0 if asset_health == "down" else None,
        "unit": None,
        "message": f"Asset health is {asset_health}",
        "updated_at": updated,
    })

    if agent is not None:
        online = is_agent_online(agent)
        state, threshold = state_from_rule(1.0 if online else 0.0, rules.get("sentinel_agent_up"))
        if not online and state == "ok":
            state = "critical"
        services.append({
            "host_id": device.id,
            "hostname": hostname,
            "service_key": "agent:health",
            "service_name": "Sentinel Agent",
            "state": state,
            "value": "online" if online else "offline",
            "unit": None,
            "message": f"Agent {agent.version} is {'online' if online else 'offline'}",
            "updated_at": agent.last_checkin,
        })

    monitors = list(
        db.execute(
            select(AgentlessMonitor)
            .where(
                AgentlessMonitor.device_id == device.id,
                AgentlessMonitor.enabled.is_(True),
            )
            .order_by(AgentlessMonitor.method, AgentlessMonitor.created_at)
        ).scalars()
    )
    for monitor in monitors:
        health = remote_monitor_health(monitor, now)
        monitor_state = "ok" if health == "up" else "critical" if health == "down" else "unknown"
        services.append({
            "host_id": device.id,
            "hostname": hostname,
            "service_key": f"monitoring:{monitor.id}",
            "service_name": f"{monitor.method.upper()} monitoring",
            "state": monitor_state,
            "value": "connected" if health == "up" else "unavailable" if health == "down" else "pending",
            "unit": None,
            "message": monitor.last_error or f"{monitor.method.upper()} collector is {health}",
            "updated_at": monitor.last_success_at or monitor.last_poll_at,
        })

    if telemetry:
        metrics: Iterable[tuple[str, str, float | int | None, str | None]] = (
            ("cpu", "CPU utilization", telemetry.cpu_usage_percent, "%"),
            ("memory", "Memory utilization", telemetry.memory_usage_percent, "%"),
        )
        metric_names = {"cpu": "sentinel_cpu_usage_percent", "memory": "sentinel_memory_usage_percent"}
        for key, label, value, unit in metrics:
            state, threshold = state_from_rule(float(value) if value is not None else None, rules.get(metric_names[key]))
            services.append({
                "host_id": device.id,
                "hostname": hostname,
                "service_key": f"metric:{key}",
                "service_name": label,
                "state": state,
                "value": value,
                "unit": unit,
                "message": f"{label}: {value:.1f}{unit}" if isinstance(value, (int, float)) else f"{label}: no data",
                "updated_at": telemetry.collected_at,
            })

        for disk in telemetry.disks or []:
            mount = str(disk.get("mountpoint", "unknown"))
            value = float(disk.get("usage_percent", 0) or 0)
            state, _ = state_from_rule(value, rules.get("sentinel_disk_usage_percent"))
            services.append({
                "host_id": device.id,
                "hostname": hostname,
                "service_key": f"disk:{mount}",
                "service_name": f"Disk {mount}",
                "state": state,
                "value": value,
                "unit": "%",
                "message": f"Disk {mount} usage: {value:.1f}%",
                "updated_at": telemetry.collected_at,
            })

        if telemetry.process_count is not None:
            services.append({
                "host_id": device.id,
                "hostname": hostname,
                "service_key": "process:count",
                "service_name": "Process count",
                "state": "ok",
                "value": telemetry.process_count,
                "unit": None,
                "message": f"{telemetry.process_count} running processes",
                "updated_at": telemetry.collected_at,
            })

        for nic in telemetry.interfaces or []:
            name = str(nic.get("name", "unknown"))
            services.append({
                "host_id": device.id,
                "hostname": hostname,
                "service_key": f"interface:{name}",
                "service_name": f"Interface {name}",
                "state": "ok",
                "value": None,
                "unit": None,
                "message": "Interface counters are being collected",
                "updated_at": telemetry.collected_at,
            })

    return services


def all_services(db: Session) -> list[dict]:
    output: list[dict] = []
    for device in db.execute(select(Device).order_by(Device.hostname, Device.ip_address)).scalars():
        output.extend(services_for_device(db, device))
    return output


def sync_problems(db: Session) -> list[Problem]:
    active_keys: set[tuple[str, str]] = set()
    now = utcnow()
    rules = _rule_map(db)

    devices = list(db.execute(select(Device)).scalars())
    for device in devices:
        reconcile_device_health(db, device, now)

    for device in devices:
        suppressed = notifications_suppressed(db, device, now)
        for service in services_for_device(db, device):
            if service["state"] not in {"warning", "critical"}:
                continue

            key = (device.id, service["service_key"])
            active_keys.add(key)
            problem = db.execute(
                select(Problem).where(
                    Problem.device_id == device.id,
                    Problem.service_key == service["service_key"],
                    Problem.state != "resolved",
                )
            ).scalar_one_or_none()

            metric = None
            if service["service_key"] == "metric:cpu": metric = "sentinel_cpu_usage_percent"
            elif service["service_key"] == "metric:memory": metric = "sentinel_memory_usage_percent"
            elif service["service_key"].startswith("disk:"): metric = "sentinel_disk_usage_percent"
            elif service["service_key"] == "agent:health": metric = "sentinel_agent_up"
            rule = rules.get(metric) if metric else None
            value = service.get("value") if isinstance(service.get("value"), (int, float)) else None
            threshold = None
            if rule:
                threshold = rule.critical_threshold if service["state"] == "critical" else rule.warning_threshold

            if problem is None:
                problem = Problem(
                    device_id=device.id,
                    service_key=service["service_key"],
                    service_name=service["service_name"],
                    severity=service["state"],
                    state="suppressed" if suppressed else "open",
                    title=f"{service['service_name']} is {service['state']}",
                    message=service["message"],
                    current_value=float(value) if value is not None else None,
                    threshold=threshold,
                    opened_at=now,
                    updated_at=now,
                )
                db.add(problem)
                db.flush()
                enqueue_problem_transition(db, problem, device, "opened", now=now)
                continue

            previous_state = problem.state
            previous_severity = problem.severity
            problem.severity = service["state"]
            problem.title = f"{service['service_name']} is {service['state']}"
            problem.message = service["message"]
            problem.current_value = float(value) if value is not None else None
            problem.threshold = threshold
            problem.updated_at = now

            if suppressed:
                problem.state = "suppressed"
            elif previous_state == "suppressed":
                problem.state = "acknowledged" if problem.acknowledged_at else "open"
                enqueue_problem_transition(db, problem, device, "maintenance-ended", now=now)

            if previous_severity != problem.severity and problem.severity == "critical":
                enqueue_problem_transition(db, problem, device, "escalated", now=now)

    for problem in db.execute(select(Problem).where(Problem.state != "resolved")).scalars():
        if (problem.device_id, problem.service_key) in active_keys:
            continue
        device = db.get(Device, problem.device_id)
        problem.state = "resolved"
        problem.resolved_at = now
        problem.updated_at = now
        if device is not None:
            enqueue_problem_transition(db, problem, device, "resolved", now=now)

    db.commit()
    return list(db.execute(select(Problem).order_by(Problem.state, Problem.severity, Problem.opened_at.desc())).scalars())
