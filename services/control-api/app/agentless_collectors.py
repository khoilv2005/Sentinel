from __future__ import annotations

import io
import json
import re
import subprocess
import time
from typing import Any

import paramiko
import winrm
from winrm.exceptions import WinRMOperationTimeoutError


def _normalize(result: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "source": source,
        "hostname": result.get("hostname"),
        "os_name": result.get("os_name"),
        "cpu_usage_percent": result.get("cpu_usage_percent"),
        "memory_total_bytes": result.get("memory_total_bytes"),
        "memory_used_bytes": result.get("memory_used_bytes"),
        "memory_usage_percent": result.get("memory_usage_percent"),
        "uptime_seconds": result.get("uptime_seconds"),
        "process_count": result.get("process_count"),
        "disks": result.get("disks") or [],
        "interfaces": result.get("interfaces") or [],
        "raw": result.get("raw") or {},
    }


def collect_winrm(target: str, username: str | None, secrets: dict[str, str], options: dict) -> dict:
    password = secrets.get("password")
    if not username or not password:
        raise ValueError("WinRM requires username and password")
    domain = str(options.get("domain") or "").strip()
    auth_user = f"{domain}\\{username}" if domain and "\\" not in username and "@" not in username else username
    use_https = bool(options.get("https", False))
    port = int(options.get("port") or (5986 if use_https else 5985))
    endpoint = f"{'https' if use_https else 'http'}://{target}:{port}/wsman"
    transport = str(options.get("transport") or "ntlm")
    validation = "validate" if bool(options.get("validate_cert", False)) else "ignore"

    operation_timeout_sec = int(options.get("operation_timeout_sec") or 30)
    read_timeout_sec = int(options.get("read_timeout_sec") or max(operation_timeout_sec + 15, 45))
    if operation_timeout_sec < 1:
        raise ValueError("WinRM operation_timeout_sec must be at least 1")
    if read_timeout_sec <= operation_timeout_sec:
        raise ValueError("WinRM read_timeout_sec must exceed operation_timeout_sec")
    retries = max(0, min(int(options.get("retries", 1)), 3))

    def new_session():
        return winrm.Session(
            endpoint,
            auth=(auth_user, password),
            transport=transport,
            server_cert_validation=validation,
            operation_timeout_sec=operation_timeout_sec,
            read_timeout_sec=read_timeout_sec,
        )

    script = r'''
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$total = [double]$os.TotalVisibleMemorySize * 1024
$free = [double]$os.FreePhysicalMemory * 1024
$used = [double]($total - $free)
if ($used -lt 0) { $used = 0.0 }
$memPct = if ($total -gt 0) { [math]::Round(($used / $total) * 100, 2) } else { $null }
$disks = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
  $usedDisk = [double]$_.Size - [double]$_.FreeSpace
  [pscustomobject]@{
    mountpoint = $_.DeviceID
    fstype = $_.FileSystem
    total_bytes = [int64]$_.Size
    used_bytes = [int64]$usedDisk
    usage_percent = if ($_.Size -gt 0) { [math]::Round(($usedDisk / [double]$_.Size) * 100, 2) } else { 0 }
  }
})
$interfaces = @()
try {
  $interfaces = @(Get-NetAdapterStatistics -ErrorAction Stop | ForEach-Object {
    [pscustomobject]@{ name=$_.Name; receive_bytes_total=[int64]$_.ReceivedBytes; transmit_bytes_total=[int64]$_.SentBytes }
  })
} catch {}
$uptime = [int64]((Get-Date) - $os.LastBootUpTime).TotalSeconds
[pscustomobject]@{
  hostname = $env:COMPUTERNAME
  os_name = $os.Caption
  cpu_usage_percent = [double]$cpu
  memory_total_bytes = [int64]$total
  memory_used_bytes = [int64]$used
  memory_usage_percent = $memPct
  uptime_seconds = $uptime
  process_count = @(Get-Process).Count
  disks = $disks
  interfaces = $interfaces
} | ConvertTo-Json -Compress -Depth 5
'''

    result = None
    for attempt in range(retries + 1):
        try:
            result = new_session().run_ps(script)
            break
        except WinRMOperationTimeoutError:
            if attempt >= retries:
                raise
            time.sleep(min(1.0 + attempt, 3.0))
    if result is None:
        raise RuntimeError("WinRM returned no result")
    if result.status_code != 0:
        stderr = result.std_err.decode("utf-8", "replace").strip()
        raise RuntimeError(stderr or f"WinRM PowerShell returned {result.status_code}")
    text = result.std_out.decode("utf-8", "replace").strip()
    if not text:
        raise RuntimeError("WinRM returned no telemetry")
    data = json.loads(text)
    data["raw"] = {
        "transport": transport,
        "endpoint": endpoint,
        "operation_timeout_sec": operation_timeout_sec,
        "read_timeout_sec": read_timeout_sec,
    }
    return _normalize(data, "winrm")


def _ssh_key(value: str):
    errors = []
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return cls.from_private_key(io.StringIO(value))
        except Exception as exc:
            errors.append(str(exc))
    raise ValueError("SSH private key format is not supported: " + "; ".join(errors[-2:]))


def _ssh_exec(client: paramiko.SSHClient, command: str, timeout: float = 8.0) -> str:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace").strip()
    if code != 0:
        raise RuntimeError(err or f"SSH command failed with exit code {code}")
    return out.strip()


def _cpu_sample(text: str) -> tuple[int, int]:
    parts = text.strip().split()
    if not parts or parts[0] != "cpu":
        raise ValueError("invalid /proc/stat sample")
    nums = [int(v) for v in parts[1:]]
    total = sum(nums)
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    return total, idle


def collect_ssh(target: str, username: str | None, secrets: dict[str, str], options: dict) -> dict:
    if not username:
        raise ValueError("SSH requires username")
    port = int(options.get("port") or 22)
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    if bool(options.get("strict_host_key", False)):
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs: dict[str, Any] = {
        "hostname": target,
        "port": port,
        "username": username,
        "timeout": float(options.get("timeout") or 6),
        "banner_timeout": 6,
        "auth_timeout": 6,
    }
    if secrets.get("private_key"):
        kwargs["pkey"] = _ssh_key(secrets["private_key"])
    else:
        kwargs["password"] = secrets.get("password")
    client.connect(**kwargs)
    try:
        hostname = _ssh_exec(client, "hostname")
        os_name = _ssh_exec(client, "uname -srm")
        stat1 = _cpu_sample(_ssh_exec(client, "head -n 1 /proc/stat"))
        time.sleep(0.5)
        stat2 = _cpu_sample(_ssh_exec(client, "head -n 1 /proc/stat"))
        total_delta = max(1, stat2[0] - stat1[0])
        idle_delta = max(0, stat2[1] - stat1[1])
        cpu = round(max(0.0, min(100.0, (1.0 - idle_delta / total_delta) * 100.0)), 2)

        meminfo = _ssh_exec(client, "cat /proc/meminfo")
        mem: dict[str, int] = {}
        for line in meminfo.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            match = re.search(r"(\d+)", value)
            if match:
                mem[key] = int(match.group(1)) * 1024
        total_mem = mem.get("MemTotal", 0)
        available = mem.get("MemAvailable", mem.get("MemFree", 0))
        used_mem = max(0, total_mem - available)
        mem_pct = round((used_mem / total_mem) * 100, 2) if total_mem else None

        disks = []
        for line in _ssh_exec(client, "df -P -B1 2>/dev/null | tail -n +2").splitlines():
            parts = line.split()
            if len(parts) < 6:
                continue
            try:
                disks.append({
                    "mountpoint": parts[5], "fstype": "", "total_bytes": int(parts[1]),
                    "used_bytes": int(parts[2]), "usage_percent": float(parts[4].rstrip("%")),
                })
            except ValueError:
                continue

        interfaces = []
        for line in _ssh_exec(client, "cat /proc/net/dev").splitlines()[2:]:
            if ":" not in line:
                continue
            name, values = line.split(":", 1)
            cols = values.split()
            if len(cols) >= 9:
                interfaces.append({
                    "name": name.strip(), "receive_bytes_total": int(cols[0]), "transmit_bytes_total": int(cols[8]),
                })
        uptime = int(float(_ssh_exec(client, "cut -d' ' -f1 /proc/uptime")))
        processes = int(_ssh_exec(client, "ps -e --no-headers 2>/dev/null | wc -l"))
        return _normalize({
            "hostname": hostname,
            "os_name": os_name,
            "cpu_usage_percent": cpu,
            "memory_total_bytes": total_mem,
            "memory_used_bytes": used_mem,
            "memory_usage_percent": mem_pct,
            "uptime_seconds": uptime,
            "process_count": processes,
            "disks": disks,
            "interfaces": interfaces,
            "raw": {"port": port},
        }, "ssh")
    finally:
        client.close()


def _snmp_base(target: str, username: str | None, secrets: dict[str, str], options: dict) -> list[str]:
    version = str(options.get("version") or ("3" if username else "2c"))
    timeout = str(options.get("timeout") or 2)
    retries = str(options.get("retries") or 1)
    if version in {"2", "2c"}:
        community = secrets.get("community")
        if not community:
            raise ValueError("SNMP v2c requires community")
        return ["snmpget", "-v2c", "-c", community, "-t", timeout, "-r", retries, "-Oqv", target]
    if version != "3":
        raise ValueError(f"unsupported SNMP version {version}")
    if not username:
        raise ValueError("SNMPv3 requires username")
    level = str(options.get("security_level") or "authPriv")
    cmd = ["snmpget", "-v3", "-l", level, "-u", username]
    auth = secrets.get("auth_password")
    priv = secrets.get("privacy_password")
    if "auth" in level.lower():
        if not auth:
            raise ValueError("SNMPv3 auth level requires auth password")
        cmd += ["-a", str(options.get("auth_protocol") or "SHA"), "-A", auth]
    if "priv" in level.lower():
        if not priv:
            raise ValueError("SNMPv3 privacy level requires privacy password")
        cmd += ["-x", str(options.get("privacy_protocol") or "AES"), "-X", priv]
    cmd += ["-t", timeout, "-r", retries, "-Oqv", target]
    return cmd


def _run_snmp(cmd: list[str], oids: list[str], timeout: float = 8.0) -> list[str]:
    proc = subprocess.run(cmd + oids, capture_output=True, text=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "SNMP query failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def collect_snmp(target: str, username: str | None, secrets: dict[str, str], options: dict) -> dict:
    base = _snmp_base(target, username, secrets, options)
    values = _run_snmp(base, ["1.3.6.1.2.1.1.5.0", "1.3.6.1.2.1.1.3.0"])
    hostname = values[0].strip('"') if values else target
    uptime = None
    if len(values) > 1:
        match = re.search(r"\((\d+)\)", values[1]) or re.search(r"(\d+)", values[1])
        if match:
            uptime = int(match.group(1)) / 100.0
    cpu = None
    walk = base.copy()
    walk[0] = "snmpwalk"
    try:
        cpu_values = _run_snmp(walk, ["1.3.6.1.2.1.25.3.3.1.2"], timeout=8.0)
        parsed = [float(m.group(1)) for line in cpu_values if (m := re.search(r"(-?\d+(?:\.\d+)?)", line))]
        if parsed:
            cpu = round(sum(parsed) / len(parsed), 2)
    except Exception:
        pass
    return _normalize({
        "hostname": hostname,
        "os_name": "SNMP device",
        "cpu_usage_percent": cpu,
        "uptime_seconds": int(uptime) if uptime is not None else None,
        "raw": {"snmp": True},
    }, "snmp")


def collect_target(method: str, target: str, username: str | None, secrets: dict[str, str], options: dict) -> dict:
    if method == "winrm":
        return collect_winrm(target, username, secrets, options)
    if method == "ssh":
        return collect_ssh(target, username, secrets, options)
    if method == "snmp":
        return collect_snmp(target, username, secrets, options)
    raise ValueError(f"unsupported agentless method: {method}")
