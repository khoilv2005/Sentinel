import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import Device, Event, ScanJob
from .netutils import inspect_host, parse_private_network

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sentinel-discovery")
Base.metadata.create_all(bind=engine)


def utcnow():
    return datetime.now(timezone.utc)


def run_job(job_id: str):
    """Discover asset identity only.

    Discovery is intentionally not a health authority. A scan may observe a
    device and enrich inventory metadata, but it must not force Device.state to
    up/down. Runtime health belongs to configured monitoring methods (managed
    agent, WinRM, SSH, SNMP, ICMP/blackbox) and their service/problem state.
    """
    db = SessionLocal()
    try:
        job = db.get(ScanJob, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = utcnow()
        db.commit()

        net = parse_private_network(job.cidr)
        hosts = [str(ip) for ip in net.hosts()]
        found = 0

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
                    d = db.execute(
                        select(Device).where(Device.ip_address == result["ip_address"])
                    ).scalar_one_or_none()
                    is_new = d is None
                    if is_new:
                        d = Device(
                            ip_address=result["ip_address"],
                            first_seen=utcnow(),
                            state="unknown",
                        )
                        db.add(d)
                        db.flush()

                    d.hostname = result["hostname"] or d.hostname
                    d.mac_address = result["mac_address"] or d.mac_address
                    d.latency_ms = result["latency_ms"]
                    d.open_ports = result["open_ports"]
                    if d.device_class in {None, "unknown"}:
                        d.device_class = result["device_class"]
                    d.last_seen = utcnow()
                    d.site = job.site or d.site

                    db.add(Event(
                        device_id=d.id,
                        severity="info",
                        event_type="device_discovered" if is_new else "device_seen",
                        message=f"{'Discovered' if is_new else 'Observed'} {result['ip_address']}",
                        details={
                            "ports": result["open_ports"],
                            "scan_id": job.id,
                            "source": "discovery",
                            "health_changed": False,
                        },
                    ))

                job.scanned = i
                job.discovered = found
                if i % 25 == 0 or result:
                    db.commit()

        job.status = "complete"
        job.discovered = found
        job.scanned = len(hosts)
        job.finished_at = utcnow()
        db.commit()
        log.info("scan %s complete: %s/%s devices", job.id, found, len(hosts))
    except Exception as exc:
        log.exception("scan %s failed", job_id)
        job = db.get(ScanJob, job_id)
        if job:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = utcnow()
            db.commit()
    finally:
        db.close()


def loop():
    log.info("SentinelView discovery worker started")
    while True:
        db = SessionLocal()
        job = db.execute(
            select(ScanJob)
            .where(ScanJob.status == "pending")
            .order_by(ScanJob.created_at)
            .limit(1)
        ).scalar_one_or_none()
        jid = job.id if job else None
        if job:
            job.status = "claimed"
            db.commit()
        db.close()
        if jid:
            run_job(jid)
        else:
            time.sleep(2)


if __name__ == "__main__":
    loop()
