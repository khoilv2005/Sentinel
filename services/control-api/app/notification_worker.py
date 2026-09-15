from __future__ import annotations

import logging
import time

from .config import settings
from .db import Base, SessionLocal, engine
from .notification_engine import process_due_deliveries


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
log = logging.getLogger("sentinel-notifications")
Base.metadata.create_all(bind=engine)


def loop() -> None:
    interval = max(1.0, float(getattr(settings, "notification_poll_seconds", 2.0)))
    batch = max(1, min(500, int(getattr(settings, "notification_batch_size", 100))))
    log.info("SentinelView notification worker started; poll=%ss batch=%s", interval, batch)
    while True:
        db = SessionLocal()
        try:
            processed = process_due_deliveries(db, batch)
            if processed:
                log.info("processed %s notification delivery item(s)", processed)
        except Exception:
            db.rollback()
            log.exception("notification worker iteration failed")
        finally:
            db.close()
        time.sleep(interval)


if __name__ == "__main__":
    loop()
