from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import AgentTelemetryLatest, AlertRule, Device, ManagedAgent, Problem


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
    return {
        rule.metric: rule
        for rule in db.execute(select(AlertRule).where(AlertRule.enabled.is_(True))).scalars()
    }


def services_for_device(db: Session, device: Device) -> list[dict]:
    rules = _rule_map(db)
    agent = db.execute(select(ManagedAgent).where(ManagedAgent.device_id == device.id)).scalar_one_or_none()
    telemetry = db.get(AgentTelemetryLatest, agent.id) if agent else None
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

    if device.agent_enabled:
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
            "message": f"Agent {agent.version if agent else 'not enrolled'} is {'online' if online else 'offline'}",
            "updated_at": agent.last_checkin if agent else device.agent_last_seen,
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
    for device in db.execute(select(Device)).scalars():
        rules = _rule_map(db)
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
                    state="open",
                    title=f"{service['service_name']} is {service['state']}",
                    message=service["message"],
                    current_value=float(value) if value is not None else None,
                    threshold=threshold,
                    opened_at=now,
                    updated_at=now,
                )
                db.add(problem)
            else:
                problem.severity = service["state"]
                problem.title = f"{service['service_name']} is {service['state']}"
                problem.message = service["message"]
                problem.current_value = float(value) if value is not None else None
                problem.threshold = threshold
                problem.updated_at = now

    for problem in db.execute(select(Problem).where(Problem.state != "resolved")).scalars():
        if (problem.device_id, problem.service_key) not in active_keys:
            problem.state = "resolved"
            problem.resolved_at = now
            problem.updated_at = now
    db.commit()
    return list(db.execute(select(Problem).order_by(Problem.state, Problem.severity, Problem.opened_at.desc())).scalars())
