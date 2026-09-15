from __future__ import annotations

import re
from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        raise SystemExit(f"patch anchor missing in {path}: {old[:160]!r}")
    write(path, text.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"regex patch expected exactly one match in {path}: {pattern!r}, got {count}")
    write(path, updated)


# NotificationDelivery lives in a separate additive table module so existing
# v0.3.0 databases upgrade through CREATE TABLE without ALTER TABLE.
replace_once(
    "services/control-api/app/notification_engine.py",
    "from .models import Device, NotificationChannel, NotificationDelivery, Problem\n",
    "from .models import Device, NotificationChannel, Problem\nfrom .notification_models import NotificationDelivery\n",
)
replace_once(
    "services/control-api/app/notification_api.py",
    "from .models import NotificationChannel, NotificationDelivery\n",
    "from .models import NotificationChannel\nfrom .notification_models import NotificationDelivery\n",
)

main = "services/control-api/app/main.py"
replace_once(
    main,
    "from .agentless_api import router as agentless_router\n",
    "from .agentless_api import router as agentless_router\n"
    "from .notification_api import router as notification_router\n"
    "from .maintenance_engine import availability_for_device as maintenance_availability_for_device\n"
    "from .notification_engine import redact_config, validate_channel_config\n",
)
replace_once(
    main,
    "app.include_router(agentless_router)\n\nAPI_REQUESTS = Counter(",
    "app.include_router(agentless_router)\napp.include_router(notification_router)\n\nAPI_REQUESTS = Counter(",
)

# BUG-001 from the audit: default rules are identified by their unique names,
# not by a metric that is intentionally allowed to have multiple rules.
replace_once(
    main,
    "exists = db.execute(select(AlertRule).where(AlertRule.metric == metric)).scalar_one_or_none()",
    "exists = db.execute(select(AlertRule).where(AlertRule.name == name)).scalar_one_or_none()",
)

notification_old = '''@app.get("/api/v1/notification-channels", response_model=list[NotificationChannelOut])
def list_notification_channels(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    return list(db.execute(select(NotificationChannel).order_by(NotificationChannel.name)).scalars())


@app.post("/api/v1/notification-channels", response_model=NotificationChannelOut)
def create_notification_channel(payload: NotificationChannelCreate, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    if db.execute(select(NotificationChannel).where(NotificationChannel.name == payload.name)).scalar_one_or_none():
        raise HTTPException(409, "notification channel name already exists")
    row = NotificationChannel(**payload.model_dump()); db.add(row); db.flush()
    add_audit(db, identity["username"], "create", "notification_channel", row.id, f"Created channel {row.name}", {"type": row.channel_type})
    db.commit(); db.refresh(row); return row
'''
notification_new = '''def _notification_channel_out(row: NotificationChannel) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "channel_type": row.channel_type,
        "enabled": row.enabled,
        "config": redact_config(row.config or {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@app.get("/api/v1/notification-channels", response_model=list[NotificationChannelOut])
def list_notification_channels(identity: dict = Depends(control_identity), db: Session = Depends(get_db)):
    rows = db.execute(select(NotificationChannel).order_by(NotificationChannel.name)).scalars()
    return [_notification_channel_out(row) for row in rows]


@app.post("/api/v1/notification-channels", response_model=NotificationChannelOut)
def create_notification_channel(payload: NotificationChannelCreate, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    if db.execute(select(NotificationChannel).where(NotificationChannel.name == payload.name)).scalar_one_or_none():
        raise HTTPException(409, "notification channel name already exists")
    try:
        validate_channel_config(payload.channel_type, payload.config)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    row = NotificationChannel(**payload.model_dump())
    db.add(row); db.flush()
    add_audit(db, identity["username"], "create", "notification_channel", row.id, f"Created channel {row.name}", {"type": row.channel_type})
    db.commit(); db.refresh(row)
    return _notification_channel_out(row)
'''
replace_once(main, notification_old, notification_new)

maintenance_old = '''@app.post("/api/v1/maintenance", response_model=MaintenanceOut)
def create_maintenance(payload: MaintenanceCreate, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    if payload.ends_at <= payload.starts_at: raise HTTPException(400, "ends_at must be after starts_at")
    row = MaintenanceWindow(**payload.model_dump(), created_by=identity["username"]); db.add(row); db.flush()
    add_audit(db, identity["username"], "create", "maintenance", row.id, f"Created maintenance {row.name}")
    db.commit(); db.refresh(row); return row
'''
maintenance_new = '''@app.post("/api/v1/maintenance", response_model=MaintenanceOut)
def create_maintenance(payload: MaintenanceCreate, identity: dict = Depends(require_write), db: Session = Depends(get_db)):
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(400, "ends_at must be after starts_at")
    if payload.device_id and db.get(Device, payload.device_id) is None:
        raise HTTPException(404, "maintenance target device not found")
    row = MaintenanceWindow(**payload.model_dump(), created_by=identity["username"])
    db.add(row); db.flush()
    add_audit(db, identity["username"], "create", "maintenance", row.id, f"Created maintenance {row.name}")
    db.commit(); db.refresh(row)
    sync_problems(db)
    return row
'''
replace_once(main, maintenance_old, maintenance_new)

# Replace the old availability calculator with the maintenance-aware engine.
regex_once(
    main,
    r"def _availability_for_device\(db: Session, device: Device, hours: int\) -> float:\n.*?(?=\n\n@app\.get\(\"/api/v1/availability\"\))",
    '''def _availability_for_device(db: Session, device: Device, hours: int) -> float | None:\n    return maintenance_availability_for_device(db, device, hours)\n''',
)
replace_once(
    main,
    '''        targets = [r for r in rows if (sla.device_id is None or r["device_id"] == sla.device_id) and (sla.site is None or r["site"] == sla.site)]
        current = round(sum(r["availability_30d"] for r in targets) / len(targets), 4) if targets else None
        slas.append({"id": sla.id, "name": sla.name, "target_percent": sla.target_percent, "current_percent": current, "status": "pass" if current is not None and current >= sla.target_percent else "fail" if current is not None else "unknown"})
    return {"hosts": rows, "slas": slas, "history_note": "Availability history becomes authoritative from v0.3.0 state-change events onward."}
''',
    '''        targets = [r for r in rows if (sla.device_id is None or r["device_id"] == sla.device_id) and (sla.site is None or r["site"] == sla.site)]
        values = [r["availability_30d"] for r in targets if r["availability_30d"] is not None]
        current = round(sum(values) / len(values), 4) if values else None
        slas.append({"id": sla.id, "name": sla.name, "target_percent": sla.target_percent, "current_percent": current, "status": "pass" if current is not None and current >= sla.target_percent else "fail" if current is not None else "unknown"})
    return {"hosts": rows, "slas": slas, "history_note": "Availability is calculated from state-change events; active maintenance windows marked exclude_from_sla are removed from the SLA accounting denominator."}
''',
)
replace_once(
    main,
    '''            "services": True, "rules": True, "topology": True, "maintenance": True, "availability": True,
            "local_rbac": True, "grafana_optional_ui": True,
''',
    '''            "services": True, "rules": True, "topology": True, "maintenance": True, "availability": True,
            "notification_dispatch": True, "maintenance_suppression": True, "sla_maintenance_exclusion": True,
            "local_rbac": True, "grafana_optional_ui": True,
''',
)

worker = "services/control-api/app/agentless_worker.py"
replace_once(
    worker,
    "from .models import AgentlessMonitor, AgentlessTelemetryLatest, CredentialProfile, Device, Event\n",
    "from .models import AgentlessMonitor, AgentlessTelemetryLatest, CredentialProfile, Device, Event\nfrom .monitoring import sync_problems\n",
)
replace_once(
    worker,
    '''            db.add(Event(device_id=device.id, severity="info", event_type="agentless_poll",
                         message=f"Collected {monitor.method} telemetry from {device.hostname or device.ip_address}",
                         details={"method": monitor.method}))
            db.commit()
''',
    '''            db.add(Event(device_id=device.id, severity="info", event_type="agentless_poll",
                         message=f"Collected {monitor.method} telemetry from {device.hostname or device.ip_address}",
                         details={"method": monitor.method}))
            db.commit()
            sync_problems(db)
''',
)
replace_once(
    worker,
    '''            db.commit()
            log.warning("%s poll failed for %s: %s", monitor.method, device.ip_address if device else monitor.device_id, exc)
''',
    '''            db.commit()
            sync_problems(db)
            log.warning("%s poll failed for %s: %s", monitor.method, device.ip_address if device else monitor.device_id, exc)
''',
)

compose = "docker-compose.yml"
compose_text = read(compose)
if "  notification-worker:" not in compose_text:
    anchor = "  web-ui:\n"
    if anchor not in compose_text:
        raise SystemExit("web-ui compose anchor missing")
    service = '''  notification-worker:
    image: sentinelview-control-api:0.3.0
    build:
      context: .
      dockerfile: services/control-api/Dockerfile
    command: ["python", "-m", "app.notification_worker"]
    environment:
      SENTINEL_DB_URL: ${SENTINEL_DB_URL:-postgresql+psycopg://sentinel:sentinel@postgres:5432/sentinel}
      SENTINEL_LOG_LEVEL: ${SENTINEL_LOG_LEVEL:-INFO}
      SENTINEL_NOTIFICATION_POLL_SECONDS: ${SENTINEL_NOTIFICATION_POLL_SECONDS:-2}
      SENTINEL_NOTIFICATION_BATCH_SIZE: ${SENTINEL_NOTIFICATION_BATCH_SIZE:-100}
    depends_on:
      postgres:
        condition: service_healthy
      control-api:
        condition: service_healthy
    restart: unless-stopped

'''
    write(compose, compose_text.replace(anchor, service + anchor, 1))

# Add a safe full-/24 regression using the ephemeral SQLite test database.
test_agentless = "services/control-api/tests/test_agentless.py"
test_text = read(test_agentless)
if "def test_agentless_entire_24_creates_254_unique_assignments" not in test_text:
    test_text += '''


def test_agentless_entire_24_creates_254_unique_assignments():
    from app.db import SessionLocal
    from app.models import AgentlessMonitor, CredentialProfile, Device

    suffix = uuid.uuid4().hex[:8]
    credential = client.post("/api/v1/credentials", headers=ADMIN, json={
        "name": f"cidr24-{suffix}", "credential_type": "ssh_password", "username": "monitor",
        "secret": "not-a-real-password", "options": {"port": 22},
    })
    assert credential.status_code == 200, credential.text
    credential_id = credential.json()["id"]
    cidr = "10.254.17.0/24"

    first = client.post("/api/v1/agentless/monitors/bulk", headers=ADMIN, json={
        "method": "ssh", "credential_id": credential_id, "scope": "cidr_all",
        "cidr": cidr, "site": "cidr24-test", "interval_seconds": 60,
    })
    assert first.status_code == 200, first.text
    assert first.json() == {"targets": 254, "created": 254, "updated": 0}

    second = client.post("/api/v1/agentless/monitors/bulk", headers=ADMIN, json={
        "method": "ssh", "credential_id": credential_id, "scope": "cidr_all",
        "cidr": cidr, "site": "cidr24-test", "interval_seconds": 120,
    })
    assert second.status_code == 200, second.text
    assert second.json() == {"targets": 254, "created": 0, "updated": 254}

    db = SessionLocal()
    try:
        credential_row = db.get(CredentialProfile, credential_id)
        device_ids = [d.id for d in db.query(Device).filter(Device.site == "cidr24-test").all()]
        monitors = db.query(AgentlessMonitor).filter(AgentlessMonitor.device_id.in_(device_ids)).all() if device_ids else []
        assert len(device_ids) == 254
        assert len(monitors) == 254
        for monitor in monitors:
            db.delete(monitor)
        for device in db.query(Device).filter(Device.site == "cidr24-test").all():
            db.delete(device)
        if credential_row:
            db.delete(credential_row)
        db.commit()
    finally:
        db.close()
'''
    write(test_agentless, test_text)

# UI: remove stale "foundation only" claims and expose recent deliveries/test actions.
app_js = "services/web-ui/js/app.js"
text = read(app_js)
text = text.replace(
    "notifications: ['Notifications', 'Notification channels and routing foundation'],",
    "notifications: ['Notifications', 'Notification channels, delivery status and routing'],",
)
text = text.replace(
    "maintenance: ['Maintenance', 'Scheduled maintenance and alert suppression metadata'],",
    "maintenance: ['Maintenance', 'Scheduled alert suppression and SLA exclusions'],",
)

notification_function = r'''async function renderNotifications\(\) \{.*?\n\}\n\nasync function renderMaintenance\(\) \{'''
notification_replacement = '''async function renderNotifications() {
  const [channels,deliveries]=await Promise.all([api('/api/v1/notification-channels'),api('/api/v1/notification-deliveries?limit=50')]);
  const statusRows=deliveries.map(d=>`<tr><td>${badge(d.status)}</td><td>${esc(d.transition)}</td><td>${esc(d.severity)}</td><td>${esc(channels.find(c=>c.id===d.channel_id)?.name||d.channel_id)}</td><td>${d.attempts}</td><td>${esc(d.last_error||'—')}</td><td>${fmtDate(d.created_at)}</td></tr>`).join('')||`<tr><td colspan="7">${empty('No notification deliveries yet.')}</td></tr>`;
  content.innerHTML=`<div class="page-stack"><div class="grid-2"><article class="panel"><div class="panel-head"><div><h2>Add notification channel</h2><p>Webhook, Slack, Teams, Telegram or SMTP delivery</p></div></div><div class="panel-body"><form id="channel-form" class="form-stack"><label>Name<input id="channel-name" required placeholder="NOC webhook"/></label><label>Type<select id="channel-type"><option value="webhook">Webhook</option><option value="email">Email</option><option value="slack">Slack</option><option value="teams">Microsoft Teams</option><option value="telegram">Telegram</option></select></label><label>Configuration JSON<textarea id="channel-config" placeholder='{"url":"https://..."}'>{}</textarea></label><button class="button primary" type="submit">Create channel</button></form></div></article><article class="panel"><div class="panel-head"><div><h2>Routing</h2><p>Automatic problem lifecycle delivery is enabled</p></div></div><div class="panel-body"><div class="notice">Problem open, escalation, recovery and post-maintenance transitions are queued automatically. Failed deliveries use bounded exponential retry; active maintenance can suppress delivery.</div></div></article></div><article class="panel"><div class="panel-head"><div><h2>Channels</h2><p>${channels.length} configured</p></div></div><div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Status</th><th>Updated</th><th>Actions</th></tr></thead><tbody>${channels.map(c=>`<tr><td><strong>${esc(c.name)}</strong></td><td>${esc(c.channel_type)}</td><td>${badge(c.enabled?'up':'unknown',c.enabled?'enabled':'disabled')}</td><td>${fmtDate(c.updated_at)}</td><td><button class="link-button" data-test-channel="${esc(c.id)}">Test</button> <button class="link-button danger" data-delete-channel="${esc(c.id)}">Delete</button></td></tr>`).join('')||`<tr><td colspan="5">${empty('No notification channels configured.')}</td></tr>`}</tbody></table></div></article><article class="panel"><div class="panel-head"><div><h2>Recent deliveries</h2><p>Last 50 queued, sent, suppressed or failed notifications</p></div></div><div class="table-wrap"><table><thead><tr><th>Status</th><th>Transition</th><th>Severity</th><th>Channel</th><th>Attempts</th><th>Last error</th><th>Created</th></tr></thead><tbody>${statusRows}</tbody></table></div></article></div>`;
  $('#channel-form').onsubmit=async event=>{event.preventDefault();try{let config={};try{config=JSON.parse($('#channel-config').value||'{}');}catch{throw new Error('Configuration must be valid JSON');}await api('/api/v1/notification-channels',{method:'POST',body:JSON.stringify({name:$('#channel-name').value.trim(),channel_type:$('#channel-type').value,enabled:true,config})});toast('Notification channel created');await renderNotifications();}catch(e){toast(e.message,true);}};
  $$('[data-test-channel]').forEach(btn=>btn.onclick=async()=>{try{const result=await api(`/api/v1/notification-channels/${btn.dataset.testChannel}/test`,{method:'POST'});toast(`Test delivery: ${result.status}`);await renderNotifications();}catch(e){toast(e.message,true);}});
  $$('[data-delete-channel]').forEach(btn=>btn.onclick=async()=>{if(!confirm('Delete this notification channel?'))return;try{await api(`/api/v1/notification-channels/${btn.dataset.deleteChannel}`,{method:'DELETE'});toast('Channel deleted');await renderNotifications();}catch(e){toast(e.message,true);}});
}

async function renderMaintenance() {'''
updated, count = re.subn(notification_function, notification_replacement, text, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f"renderNotifications replacement failed: {count}")
text = updated
text = text.replace(
    "<h2>Schedule maintenance</h2><p>Record planned maintenance windows</p>",
    "<h2>Schedule maintenance</h2><p>Suppress problem notifications and optionally exclude the window from SLA accounting</p>",
)
text = text.replace(
    "Suppress notifications metadata",
    "Suppress problem notifications",
)
text = text.replace(
    "Exclude from SLA metadata",
    "Exclude from SLA accounting",
)
text = text.replace(
    "Maintenance windows are fully stored and visible in the operations UI. Problem suppression and SLA exclusion metadata are available to the platform; automated notification routing will consume them when the notification engine is enabled.",
    "Active maintenance windows suppress matching problem notifications when requested. Windows marked for SLA exclusion are removed from the eligible availability denominator. Host, site and global windows are supported.",
)
text = text.replace(
    "<td>${h.availability_24h}%</td><td>${h.availability_7d}%</td><td>${h.availability_30d}%</td>",
    "<td>${h.availability_24h==null?'—':h.availability_24h+'%'}</td><td>${h.availability_7d==null?'—':h.availability_7d+'%'}</td><td>${h.availability_30d==null?'—':h.availability_30d+'%'}</td>",
)
write(app_js, text)

styles = "services/web-ui/styles.css"
styles_text = read(styles)
if ".badge.suppressed" not in styles_text:
    styles_text = styles_text.replace(
        ".badge.acknowledged { background: #24213b; border-color: #49416d; color: #beb1ff; }",
        ".badge.acknowledged { background: #24213b; border-color: #49416d; color: #beb1ff; }\n.badge.suppressed { background: #202936; border-color: #41526a; color: #a9c5e8; }",
        1,
    )
    write(styles, styles_text)

print("Audit hardening patch applied")
