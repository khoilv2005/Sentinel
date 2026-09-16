from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .maintenance_engine import notifications_suppressed
from .models import AgentlessMonitor, AgentlessTelemetryLatest, AgentTelemetryLatest, AlertRule, Device, ManagedAgent, Problem
from .notification_engine import enqueue_problem_transition


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_agent_online(agent: ManagedAgent | None) -> bool:
    if agent is None or agent.revoked or agent.last_checkin is None:
        return False
    seen = agent.last_checkin
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    return (utcnow() - seen).total_seconds() <= settings.agent_online_seconds


def compare(value: float, operator: str, threshold: float | None) -> bool:
    if threshold is None:
        return False
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    if operator in {"=", "=="}:
        return value == threshold
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
    # Newer rules intentionally override older rules for the same metric. This
    # also makes duplicate-metric rules deterministic rather than depending on
    # database iteration order.
    rules = list(db.execute(
        select(AlertRule)
        .where(AlertRule.enabled.is_(True))
        .order_by(AlertRule.created_at, AlertRule.id)
    ).scalars())
    return {rule.metric: rule for rule in rules}


def latest_telemetry_for_device(db: Session, device: Device):
    agent = db.execute(select(ManagedAgent).where(ManagedAgent.device_id == device.id)).scalar_one_or_none()
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
    agent = db.execute(select(ManagedAgent).where(ManagedAgent.device_id == device.id)).scalar_one_or_none()
    telemetry, telemetry_source = latest_telemetry_for_device(db, device)
    hostname = device.hostname or device.ip_address
    updated = (telemetry.collected_at if telemetry else device.last_seen)
    services: list[dict] = []

    host_state = "ok" if device.state == "up" else "critical" if device.state == "down" else "unknown"
    services.append({
        "host_id": device.id,
        "hostname": hostname,
        "service_key": "host:availability",
        "service_name": "Host availability",
        "state": host_state,
        "value": 1 if device.state == "up" else 0,
        "unit": None,
        "message": "Host is reachable" if device.state == "up" else f"Host state is {device.state}",
        "updated_at": device.last_seen,
    })

    # A Sentinel Agent service exists only after a real managed-agent enrollment.
    # Legacy/stale Device.agent_enabled flags must never create a fake agent.
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

    monitor = db.execute(
        select(AgentlessMonitor)
        .where(AgentlessMonitor.device_id == device.id, AgentlessMonitor.enabled.is_(True))
        .order_by(AgentlessMonitor.updated_at.desc())
    ).scalars().first()
    if monitor is not None:
        now = utcnow()
        success = monitor.last_success_at
        if success is not None and success.tzinfo is None:
            success = success.replace(tzinfo=timezone.utc)
        stale = success is None or (now - success).total_seconds() > max(120, monitor.interval_seconds * 3)
        monitor_state = "critical" if stale and monitor.consecutive_failures >= 3 else "unknown" if success is None else "ok"
        services.append({
            "host_id": device.id,
            "hostname": hostname,
            "service_key": f"agentless:{monitor.method}",
            "service_name": f"{monitor.method.upper()} monitoring",
            "state": monitor_state,
            "value": "connected" if monitor_state == "ok" else "unavailable" if monitor_state == "critical" else "pending",
            "unit": None,
            "message": monitor.last_error or f"{monitor.method.upper()} collector is healthy",
            "updated_at": monitor.last_success_at or monitor.last_poll_at,
        })

    if telemetry:
        metrics: Iterable[tuple[str, str, float | int | None, str | None]] = (
            ("cpu", "CPU utilization", telemetry.cpu_usage_percent, "%"),
            ("memory", "Memory utilization", telemetry.memory_usage_percent, "%"),
        )
        metric_names = {
            "cpu": "sentinel_cpu_usage_percent",
            "memory": "sentinel_memory_usage_percent",
        }
        for key, label, value, unit in metrics:
            state, threshold = state_from_rule(float(value) if value is not None else None, rules.get(metric_names[key]))
            services.append({
                "host_id": device.id, "hostname": hostname, "service_key": f"metric:{key}",
                "service_name": label, "state": state, "value": value, "unit": unit,
                "message": f"{label}: {value:.1f}{unit}" if isinstance(value, (int, float)) else f"{label}: no data",
                "updated_at": telemetry.collected_at,
            })

        for disk in telemetry.disks or []:
            mount = str(disk.get("mountpoint", "unknown"))
            value = float(disk.get("usage_percent", 0) or 0)
            state, _ = state_from_rule(value, rules.get("sentinel_disk_usage_percent"))
            services.append({
                "host_id": device.id, "hostname": hostname, "service_key": f"disk:{mount}",
                "service_name": f"Disk {mount}", "state": state, "value": value, "unit": "%",
                "message": f"Disk {mount} usage: {value:.1f}%", "updated_at": telemetry.collected_at,
            })

        if telemetry.process_count is not None:
            services.append({
                "host_id": device.id, "hostname": hostname, "service_key": "process:count",
                "service_name": "Process count", "state": "ok", "value": telemetry.process_count, "unit": None,
                "message": f"{telemetry.process_count} running processes", "updated_at": telemetry.collected_at,
            })

        for nic in telemetry.interfaces or []:
            name = str(nic.get("name", "unknown"))
            services.append({
                "host_id": device.id, "hostname": hostname, "service_key": f"interface:{name}",
                "service_name": f"Interface {name}", "state": "ok", "value": None, "unit": None,
                "message": "Interface counters are being collected", "updated_at": telemetry.collected_at,
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

    for device in db.execute(select(Device)).scalars():
        suppressed = notifications_suppressed(db, device, now)
        for service in services_for_device(db, device):
            if service["state"] not in {"warning", "critical"}:
                continue

            key = (device.id, service["service_key"])
            active_keys.add(key)
            matching_problems = db.execute(
                select(Problem).where(
                    Problem.device_id == device.id,
                    Problem.service_key == service["service_key"],
                    Problem.state != "resolved",
                ).order_by(Problem.opened_at, Problem.id)
            ).scalars().all()
            problem = matching_problems[0] if matching_problems else None
            for duplicate in matching_problems[1:]:
                duplicate.state = "resolved"
                duplicate.resolved_at = now
                duplicate.updated_at = now

            metric = None
            if service["service_key"] == "metric:cpu":
                metric = "sentinel_cpu_usage_percent"
            elif service["service_key"] == "metric:memory":
                metric = "sentinel_memory_usage_percent"
            elif service["service_key"].startswith("disk:"):
                metric = "sentinel_disk_usage_percent"
            elif service["service_key"] == "agent:health":
                metric = "sentinel_agent_up"
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
