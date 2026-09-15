from __future__ import annotations

import json
import smtplib
import ssl
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .maintenance_engine import notifications_suppressed
from .models import Device, NotificationChannel, Problem
from .notification_models import NotificationDelivery
from .secretbox import decrypt_secrets, encrypt_secrets


MAX_ATTEMPTS = 5
SENSITIVE_CONFIG_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "bot_token",
    "community",
    "private_key",
    "webhook_url",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def pack_notification_config(config: dict | None) -> dict:
    payload = json.dumps(config or {}, separators=(",", ":"), sort_keys=True)
    return {"_encrypted": encrypt_secrets({"json": payload})}


def unpack_notification_config(config: dict | None) -> dict:
    stored = dict(config or {})
    token = stored.get("_encrypted")
    if not token:
        # Backward compatibility for v0.3.0 channels created before encrypted
        # notification configuration was introduced.
        return stored
    decrypted = decrypt_secrets(str(token))
    try:
        value = json.loads(decrypted.get("json", "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("notification configuration cannot be decoded") from exc
    if not isinstance(value, dict):
        raise ValueError("notification configuration must decode to an object")
    return value


def redact_config(config: dict | None) -> dict:
    output: dict = {}
    for key, value in (config or {}).items():
        normalized = str(key).lower()
        if normalized in SENSITIVE_CONFIG_KEYS or any(part in normalized for part in ("password", "secret", "token", "private_key")):
            output[key] = "***" if value not in {None, ""} else value
        elif normalized == "url" and isinstance(value, str):
            parsed = urlparse(value)
            if parsed.scheme and parsed.netloc:
                output[key] = f"{parsed.scheme}://{parsed.netloc}/***"
            else:
                output[key] = "***"
        else:
            output[key] = value
    return output


def validate_channel_config(channel_type: str, config: dict | None) -> None:
    config = config or {}
    if channel_type in {"webhook", "slack", "teams"}:
        url = str(config.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{channel_type} channel requires a valid http/https url")
        return
    if channel_type == "telegram":
        if not str(config.get("bot_token") or "").strip() or not str(config.get("chat_id") or "").strip():
            raise ValueError("telegram channel requires bot_token and chat_id")
        return
    if channel_type == "email":
        if not str(config.get("host") or "").strip():
            raise ValueError("email channel requires SMTP host")
        if not str(config.get("from") or config.get("from_address") or "").strip():
            raise ValueError("email channel requires from address")
        recipients = config.get("to")
        if not recipients:
            raise ValueError("email channel requires at least one recipient")
        return
    raise ValueError(f"unsupported notification channel type: {channel_type}")


def _problem_payload(problem: Problem, device: Device, transition: str, now: datetime) -> dict:
    return {
        "event": transition,
        "problem_id": problem.id,
        "device_id": device.id,
        "hostname": device.hostname or device.ip_address,
        "ip_address": device.ip_address,
        "site": device.site,
        "service_key": problem.service_key,
        "service_name": problem.service_name,
        "severity": problem.severity,
        "state": problem.state,
        "title": problem.title,
        "message": problem.message,
        "current_value": problem.current_value,
        "threshold": problem.threshold,
        "occurred_at": now.isoformat(),
    }


def enqueue_problem_transition(
    db: Session,
    problem: Problem,
    device: Device,
    transition: str,
    *,
    now: datetime | None = None,
) -> list[NotificationDelivery]:
    moment = aware(now) or utcnow()
    suppressed = notifications_suppressed(db, device, moment)
    payload = _problem_payload(problem, device, transition, moment)
    created: list[NotificationDelivery] = []
    channels = list(db.execute(select(NotificationChannel).where(NotificationChannel.enabled.is_(True))).scalars())
    for channel in channels:
        dedupe_key = f"{problem.id}:{transition}:{problem.severity}:{channel.id}"
        existing = db.execute(
            select(NotificationDelivery).where(NotificationDelivery.dedupe_key == dedupe_key)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        delivery = NotificationDelivery(
            dedupe_key=dedupe_key,
            channel_id=channel.id,
            problem_id=problem.id,
            device_id=device.id,
            transition=transition,
            severity=problem.severity,
            payload=payload,
            status="suppressed" if suppressed else "pending",
            attempts=0,
            next_attempt_at=None,
            last_error="suppressed by active maintenance" if suppressed else None,
            created_at=moment,
            updated_at=moment,
        )
        db.add(delivery)
        created.append(delivery)
    return created


def enqueue_test_delivery(db: Session, channel: NotificationChannel, actor: str) -> NotificationDelivery:
    now = utcnow()
    delivery = NotificationDelivery(
        dedupe_key=f"test:{uuid.uuid4().hex}:{channel.id}",
        channel_id=channel.id,
        problem_id=None,
        device_id=None,
        transition="test",
        severity="info",
        payload={
            "event": "test",
            "severity": "info",
            "title": "SentinelView test notification",
            "message": f"Notification channel '{channel.name}' is being tested by {actor}.",
            "occurred_at": now.isoformat(),
        },
        status="pending",
        attempts=0,
        created_at=now,
        updated_at=now,
    )
    db.add(delivery)
    db.flush()
    return delivery


def _message_text(payload: dict) -> str:
    severity = str(payload.get("severity") or "info").upper()
    title = str(payload.get("title") or "SentinelView notification")
    host = str(payload.get("hostname") or payload.get("ip_address") or "")
    message = str(payload.get("message") or "")
    host_part = f" [{host}]" if host else ""
    return f"[{severity}] {title}{host_part}\n{message}".strip()


def _send_email(config: dict, payload: dict) -> None:
    host = str(config.get("host") or "").strip()
    port = int(config.get("port") or (465 if config.get("ssl") else 587))
    username = config.get("username")
    password = config.get("password")
    from_address = str(config.get("from") or config.get("from_address") or "").strip()
    raw_to = config.get("to")
    recipients = [raw_to] if isinstance(raw_to, str) else list(raw_to or [])
    recipients = [str(value).strip() for value in recipients if str(value).strip()]
    message = EmailMessage()
    message["Subject"] = str(config.get("subject") or f"SentinelView: {payload.get('title', 'notification')}")
    message["From"] = from_address
    message["To"] = ", ".join(recipients)
    message.set_content(_message_text(payload))

    timeout = float(config.get("timeout") or 8)
    if bool(config.get("ssl", False)):
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context()) as smtp:
            if username:
                smtp.login(str(username), str(password or ""))
            smtp.send_message(message)
        return

    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        if bool(config.get("starttls", True)):
            smtp.starttls(context=ssl.create_default_context())
        if username:
            smtp.login(str(username), str(password or ""))
        smtp.send_message(message)


def dispatch_channel(channel: NotificationChannel, payload: dict) -> None:
    config = unpack_notification_config(channel.config)
    validate_channel_config(channel.channel_type, config)
    timeout = float(config.get("timeout") or 8)

    if channel.channel_type == "webhook":
        response = httpx.post(str(config["url"]), json=payload, timeout=timeout)
        response.raise_for_status()
        return
    if channel.channel_type == "slack":
        response = httpx.post(str(config["url"]), json={"text": _message_text(payload)}, timeout=timeout)
        response.raise_for_status()
        return
    if channel.channel_type == "teams":
        response = httpx.post(str(config["url"]), json={"text": _message_text(payload)}, timeout=timeout)
        response.raise_for_status()
        return
    if channel.channel_type == "telegram":
        token = str(config["bot_token"])
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": str(config["chat_id"]), "text": _message_text(payload)},
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("ok") is not True:
            raise RuntimeError("Telegram API rejected the notification")
        return
    if channel.channel_type == "email":
        _send_email(config, payload)
        return
    raise ValueError(f"unsupported notification channel type: {channel.channel_type}")


def process_delivery(db: Session, delivery: NotificationDelivery) -> NotificationDelivery:
    if delivery.status in {"sent", "suppressed"}:
        return delivery
    channel = db.get(NotificationChannel, delivery.channel_id)
    now = utcnow()
    delivery.attempts = int(delivery.attempts or 0) + 1
    delivery.updated_at = now
    if channel is None or not channel.enabled:
        delivery.status = "failed"
        delivery.last_error = "notification channel is missing or disabled"
        delivery.next_attempt_at = None
        db.commit()
        return delivery

    try:
        dispatch_channel(channel, dict(delivery.payload or {}))
        delivery.status = "sent"
        delivery.sent_at = now
        delivery.last_error = None
        delivery.next_attempt_at = None
    except Exception as exc:
        delivery.last_error = str(exc)[:2000]
        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "failed"
            delivery.next_attempt_at = None
        else:
            delivery.status = "pending"
            delay = min(300, 5 * (2 ** max(0, delivery.attempts - 1)))
            delivery.next_attempt_at = now + timedelta(seconds=delay)
    db.commit()
    db.refresh(delivery)
    return delivery


def process_due_deliveries(db: Session, limit: int = 100) -> int:
    now = utcnow()
    rows = list(db.execute(
        select(NotificationDelivery)
        .where(NotificationDelivery.status == "pending")
        .order_by(NotificationDelivery.created_at)
        .limit(max(1, min(1000, limit * 4)))
    ).scalars())
    processed = 0
    for delivery in rows:
        next_attempt = aware(delivery.next_attempt_at)
        if next_attempt is not None and next_attempt > now:
            continue
        process_delivery(db, delivery)
        processed += 1
        if processed >= limit:
            break
    return processed
