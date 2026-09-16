import json
from types import SimpleNamespace

import pytest
from winrm.exceptions import WinRMOperationTimeoutError

from app import agentless_collectors


def _sample_payload() -> dict:
    return {
        "hostname": "qa-winrm",
        "os_name": "Windows Server",
        "cpu_usage_percent": 12.5,
        "memory_total_bytes": 8 * 1024**3,
        "memory_used_bytes": 3 * 1024**3,
        "memory_usage_percent": 37.5,
        "uptime_seconds": 12345,
        "process_count": 123,
        "disks": [{"mountpoint": "C:", "fstype": "NTFS", "total_bytes": 100, "used_bytes": 40, "usage_percent": 40.0}],
        "interfaces": [],
    }


def test_winrm_retries_transient_operation_timeout_and_passes_timeout_options(monkeypatch):
    sessions = []
    calls = {"run_ps": 0, "sleep": 0}

    class FakeSession:
        def __init__(self, target, auth, **kwargs):
            sessions.append({"target": target, "auth": auth, "kwargs": kwargs})

        def run_ps(self, _script):
            calls["run_ps"] += 1
            if calls["run_ps"] == 1:
                raise WinRMOperationTimeoutError()
            return SimpleNamespace(
                status_code=0,
                std_err=b"",
                std_out=json.dumps(_sample_payload()).encode("utf-8"),
            )

    monkeypatch.setattr(agentless_collectors.winrm, "Session", FakeSession)
    monkeypatch.setattr(agentless_collectors.time, "sleep", lambda _seconds: calls.__setitem__("sleep", calls["sleep"] + 1))

    result = agentless_collectors.collect_winrm(
        "192.168.1.25",
        "monitor",
        {"password": "secret"},
        {
            "domain": "LAB",
            "transport": "ntlm",
            "operation_timeout_sec": 45,
            "read_timeout_sec": 60,
            "retries": 1,
        },
    )

    assert calls == {"run_ps": 2, "sleep": 1}
    assert len(sessions) == 2
    assert all(item["kwargs"]["operation_timeout_sec"] == 45 for item in sessions)
    assert all(item["kwargs"]["read_timeout_sec"] == 60 for item in sessions)
    assert sessions[0]["auth"] == ("LAB\\monitor", "secret")
    assert result["source"] == "winrm"
    assert result["hostname"] == "qa-winrm"
    assert result["raw"]["operation_timeout_sec"] == 45
    assert result["raw"]["read_timeout_sec"] == 60


def test_winrm_rejects_invalid_timeout_relationship():
    with pytest.raises(ValueError, match="read_timeout_sec must exceed operation_timeout_sec"):
        agentless_collectors.collect_winrm(
            "192.168.1.25",
            "monitor",
            {"password": "secret"},
            {"operation_timeout_sec": 30, "read_timeout_sec": 30},
        )
