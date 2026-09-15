from __future__ import annotations

import os

from app.agentless_collectors import collect_winrm


USER = os.environ.get("SENTINEL_QA_WINRM_USER", "sentinelqa")
PASSWORD = os.environ["SENTINEL_QA_WINRM_PASSWORD"]
DOMAIN = os.environ.get("SENTINEL_QA_WINRM_DOMAIN", "")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    data = collect_winrm(
        "127.0.0.1",
        USER,
        {"password": PASSWORD},
        {
            "domain": DOMAIN,
            "transport": "ntlm",
            "https": False,
            "port": 5985,
            "validate_cert": False,
        },
    )
    require(bool(data.get("hostname")), "WinRM collector did not return hostname")
    require(bool(data.get("os_name")), "WinRM collector did not return OS")
    require(data.get("cpu_usage_percent") is not None, "WinRM collector did not return CPU")
    require(int(data.get("memory_total_bytes") or 0) > 0, "WinRM collector did not return memory")
    require(data.get("memory_usage_percent") is not None, "WinRM collector did not return memory percentage")
    require(bool(data.get("disks")), "WinRM collector did not return fixed disks")
    require(data.get("uptime_seconds") is not None, "WinRM collector did not return uptime")
    require(int(data.get("process_count") or 0) > 0, "WinRM collector did not return process count")
    require(isinstance(data.get("interfaces"), list), "WinRM collector did not return interface list")
    print("agentless Windows integration PASS: WinRM/CIM telemetry")


if __name__ == "__main__":
    main()
