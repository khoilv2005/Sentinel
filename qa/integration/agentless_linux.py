from __future__ import annotations

import os

from sqlalchemy import select

from app.agentless_collectors import collect_snmp, collect_ssh
from app.agentless_worker import poll_monitor
from app.db import Base, SessionLocal, engine
from app.models import AgentlessMonitor, CredentialProfile, Device
from app.secretbox import encrypt_secrets


SSH_USER = os.environ.get("SENTINEL_QA_SSH_USER", "sentinelqa")
SSH_PASSWORD = os.environ.get("SENTINEL_QA_SSH_PASSWORD", "SentinelQa-Only-123!")
SSH_PORT = int(os.environ.get("SENTINEL_QA_SSH_PORT", "2222"))
SNMP_COMMUNITY = os.environ.get("SENTINEL_QA_SNMP_COMMUNITY", "sentinelqa")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    Base.metadata.create_all(bind=engine)

    ssh = collect_ssh(
        "127.0.0.1",
        SSH_USER,
        {"password": SSH_PASSWORD},
        {"port": SSH_PORT, "timeout": 3},
    )
    require(bool(ssh.get("hostname")), "SSH collector did not return hostname")
    require(ssh.get("cpu_usage_percent") is not None, "SSH collector did not return CPU")
    require(int(ssh.get("memory_total_bytes") or 0) > 0, "SSH collector did not return memory")
    require(bool(ssh.get("disks")), "SSH collector did not return disks")
    require(ssh.get("uptime_seconds") is not None, "SSH collector did not return uptime")
    require(int(ssh.get("process_count") or 0) > 0, "SSH collector did not return process count")
    require(bool(ssh.get("interfaces")), "SSH collector did not return network interfaces")

    snmp = collect_snmp(
        "127.0.0.1",
        None,
        {"community": SNMP_COMMUNITY},
        {"version": "2c", "timeout": 2, "retries": 0},
    )
    require(bool(snmp.get("hostname")), "SNMP collector did not return sysName")
    require(snmp.get("uptime_seconds") is not None, "SNMP collector did not return sysUpTime")

    db = SessionLocal()
    try:
        device = Device(
            ip_address="127.0.0.1",
            hostname="qa-agentless-localhost",
            device_class="server",
            state="up",
            site="ci",
        )
        credential = CredentialProfile(
            name="qa-ssh-recovery",
            credential_type="ssh_password",
            username=SSH_USER,
            secret_encrypted=encrypt_secrets({"password": SSH_PASSWORD}),
            options_json={"port": 1, "timeout": 1},
            enabled=True,
        )
        db.add_all([device, credential])
        db.flush()
        monitor = AgentlessMonitor(
            device_id=device.id,
            method="ssh",
            credential_id=credential.id,
            interval_seconds=15,
            enabled=True,
        )
        db.add(monitor)
        db.commit()
        monitor_id = monitor.id
        credential_id = credential.id
        device_id = device.id
    finally:
        db.close()

    for expected in (1, 2, 3):
        poll_monitor(monitor_id)
        db = SessionLocal()
        try:
            monitor = db.get(AgentlessMonitor, monitor_id)
            device = db.get(Device, device_id)
            require(monitor is not None, "monitor disappeared during failure test")
            require(monitor.consecutive_failures == expected, f"expected {expected} failure(s), got {monitor.consecutive_failures}")
            if expected == 3:
                require(device is not None and device.state == "down", "device did not transition down after third failure")
        finally:
            db.close()

    db = SessionLocal()
    try:
        credential = db.get(CredentialProfile, credential_id)
        require(credential is not None, "credential missing before recovery")
        credential.options_json = {"port": SSH_PORT, "timeout": 3}
        db.commit()
    finally:
        db.close()

    poll_monitor(monitor_id)
    db = SessionLocal()
    try:
        monitor = db.get(AgentlessMonitor, monitor_id)
        device = db.get(Device, device_id)
        require(monitor is not None and monitor.consecutive_failures == 0, "successful SSH poll did not reset failures")
        require(monitor.last_success_at is not None, "successful SSH poll did not update last_success_at")
        require(monitor.last_error is None, "successful SSH poll did not clear last_error")
        require(device is not None and device.state == "up", "device did not recover to up")
    finally:
        db.close()

    print("agentless Linux integration PASS: SSH + SNMP + 3-failure recovery")


if __name__ == "__main__":
    main()
