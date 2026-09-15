import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from sqlalchemy import select
from .config import settings
from .db import Base, SessionLocal, engine
from .models import Device, Event, ScanJob
from .netutils import inspect_host, parse_private_network

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
log = logging.getLogger("sentinel-discovery")
Base.metadata.create_all(bind=engine)

def utcnow():
    return datetime.now(timezone.utc)

def run_job(job_id: str):
    db = SessionLocal()
    try:
        job = db.get(ScanJob, job_id)
        if not job: return
        job.status = "running"; job.started_at = utcnow(); db.commit()
        net = parse_private_network(job.cidr)
        hosts = [str(ip) for ip in net.hosts()]
        found = 0
        found_ips = set()
        with ThreadPoolExecutor(max_workers=min(96, max(1, len(hosts)))) as ex:
            futs = {ex.submit(inspect_host, ip): ip for ip in hosts}
            for i, fut in enumerate(as_completed(futs), 1):
                result = None
                try:
                    result = fut.result()
                except Exception as exc:
                    log.debug("scan error for %s: %s", futs[fut], exc)
                if result:
                    found += 1
                    found_ips.add(result["ip_address"])
                    d = db.execute(select(Device).where(Device.ip_address == result["ip_address"])).scalar_one_or_none()
                    is_new = d is None
                    if is_new:
                        d = Device(ip_address=result["ip_address"], first_seen=utcnow())
                        db.add(d)
                        db.flush()
                    d.hostname = result["hostname"] or d.hostname
                    d.mac_address = result["mac_address"] or d.mac_address
                    d.latency_ms = result["latency_ms"]
                    d.open_ports = result["open_ports"]
                    d.device_class = result["device_class"] if d.device_class in {None, "unknown"} else d.device_class
                    previous_state = d.state
                    d.state = "up"
                    d.last_seen = utcnow()
                    if previous_state != "up":
                        db.add(Event(device_id=d.id, severity="info", event_type="state_change", message=f"{d.hostname or d.ip_address}: {previous_state} -> up", details={"from": previous_state, "to": "up", "source": "discovery"}))
                    d.site = job.site or d.site
                    db.add(Event(
                        device_id=d.id,
                        severity="info", event_type="device_discovered" if is_new else "device_seen",
                        message=f"{'Discovered' if is_new else 'Observed'} {result['ip_address']}",
                        details={"ports": result["open_ports"], "scan_id": job.id},
                    ))
                job.scanned = i; job.discovered = found
                if i % 25 == 0 or result:
                    db.commit()
        # Mark inventory entries in this scan scope as down when no probe responded.
        # Fresh agent heartbeats are treated as stronger evidence and keep a host up.
        heartbeat_cutoff = utcnow().timestamp() - settings.agent_online_seconds
        for device in db.execute(select(Device)).scalars():
            try:
                if device.ip_address not in found_ips and __import__("ipaddress").ip_address(device.ip_address) in net:
                    fresh_agent = bool(device.agent_last_seen and device.agent_last_seen.timestamp() >= heartbeat_cutoff)
                    if not fresh_agent and device.state != "down":
                        previous_state = device.state
                        device.state = "down"
                        db.add(Event(device_id=device.id, severity="critical", event_type="state_change", message=f"{device.hostname or device.ip_address}: {previous_state} -> down", details={"from": previous_state, "to": "down", "source": "discovery"}))
            except ValueError:
                continue
        job.status = "complete"; job.discovered = found; job.scanned = len(hosts); job.finished_at = utcnow(); db.commit()
        log.info("scan %s complete: %s/%s devices", job.id, found, len(hosts))
    except Exception as exc:
        log.exception("scan %s failed", job_id)
        job = db.get(ScanJob, job_id)
        if job:
            job.status = "failed"; job.error = str(exc); job.finished_at = utcnow(); db.commit()
    finally:
        db.close()

def loop():
    log.info("SentinelView discovery worker started")
    while True:
        db = SessionLocal()
        job = db.execute(select(ScanJob).where(ScanJob.status == "pending").order_by(ScanJob.created_at).limit(1)).scalar_one_or_none()
        jid = job.id if job else None
        if job:
            job.status = "claimed"; db.commit()
        db.close()
        if jid:
            run_job(jid)
        else:
            time.sleep(2)

if __name__ == "__main__":
    loop()
