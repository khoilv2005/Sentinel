import ipaddress
import re
import socket
import subprocess
import time
from .config import settings

PORT_CLASSES = {
    22: "server", 53: "network", 80: "web-device", 443: "web-device",
    445: "windows", 3389: "windows", 8006: "hypervisor", 8080: "web-device",
    8443: "web-device", 9100: "printer", 9123: "server",
}

def parse_private_network(cidr: str):
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise ValueError(f"invalid CIDR: {exc}") from exc
    if not net.is_private:
        raise ValueError("only private RFC1918/ULA/link-local networks are allowed")
    if net.num_addresses > settings.scan_max_hosts + 2:
        raise ValueError(f"network too large; maximum {settings.scan_max_hosts} usable hosts per scan")
    return net

def tcp_probe(ip: str, port: int, timeout: float = 0.20) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False

def ping(ip: str, timeout: float = 0.8):
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", str(max(1, int(timeout))), ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 0.5,
            check=False,
        )
        if proc.returncode == 0:
            return round((time.perf_counter() - start) * 1000, 2)
    except (subprocess.SubprocessError, OSError):
        pass
    return None

def reverse_dns(ip: str):
    try:
        return socket.gethostbyaddr(ip)[0]
    except OSError:
        return None

def mac_from_neigh(ip: str):
    try:
        out = subprocess.check_output(["ip", "neigh", "show", ip], text=True, timeout=1)
        match = re.search(r"lladdr\s+([0-9a-fA-F:]{17})", out)
        return match.group(1).lower() if match else None
    except Exception:
        return None

def classify_device(open_ports: list[int], hostname: str | None = None):
    ports = set(open_ports)
    h = (hostname or "").lower()
    if 8006 in ports or "proxmox" in h:
        return "hypervisor"
    if 9100 in ports or "printer" in h or "hp" in h and 9100 in ports:
        return "printer"
    if 445 in ports or 3389 in ports:
        return "windows"
    if 53 in ports and (80 in ports or 443 in ports):
        return "network"
    if 22 in ports:
        return "server"
    if ports & {80, 443, 8080, 8443}:
        return "web-device"
    return "unknown"

def inspect_host(ip: str):
    latency = ping(ip)
    # Port probes are sequential inside a host probe. Host-level parallelism is handled
    # by the discovery worker, avoiding an excessive nested thread count on /24+/16 scans.
    ports = [p for p in settings.scan_tcp_ports if tcp_probe(ip, p)]
    if latency is None and not ports:
        return None
    hostname = reverse_dns(ip)
    return {
        "ip_address": ip,
        "hostname": hostname,
        "mac_address": mac_from_neigh(ip),
        "latency_ms": latency,
        "open_ports": sorted(ports),
        "device_class": classify_device(ports, hostname),
        "state": "up",
    }
