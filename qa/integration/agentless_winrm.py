from __future__ import annotations

import os
import time

from app.agentless_collectors import collect_winrm


USER = os.environ.get("SENTINEL_QA_WINRM_USER", "sentinelqa")
PASSWORD = os.environ["SENTINEL_QA_WINRM_PASSWORD"]
DOMAIN = os.environ.get("SENTINEL_QA_WINRM_DOMAIN", "")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def collect_with_retry() -> dict:
    """Give the freshly enabled Windows runner a short WinRM settle window.

    Hosted Windows images occasionally accept authentication before the WSMan
    shell is ready and return a transient operation timeout. Retrying the real
    connection keeps this an end-to-end test without weakening collector
    assertions.
    """
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            return collect_winrm(
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
        except Exception as exc:  # real integration retry, preserve final error
            last_error = exc
            if attempt == 3:
                raise
            print(f"WinRM attempt {attempt} was not ready yet: {type(exc).__name__}; retrying")
            time.sleep(5)
    raise RuntimeError("WinRM collection failed") from last_error


def main() -> None:
    data = collect_with_retry()
    require(bool(data.get("hostname")), "WinRM collector did not return hostname")
    require(bool(data.get("os_name")), "WinRM collector did not return OS")
    require(data.get("cpu_usage_percent") is not None, "WinRM collector did not return CPU")
    require(int(data.get("memory_total_bytes") or 0) > 0, "WinRM collector did not return memory")
    require(data.get("memory_usage_percent") is not None, "WinRM collector did not return memory percentage")
    require(bool(data.get("disks")), "WinRM collector did not return fixed disks")
    require(data.get("uptime_seconds") is not None, "WinRM collector did not return uptime")
    require(int(data.get("process_count") or 0) > 0, "WinRM collector did not return process count")
    require(isinstance(data.get("interfaces"), list), "WinRM collector did not return interface list")
    print("monitoring Windows integration PASS: WinRM/CIM telemetry")


if __name__ == "__main__":
    main()
