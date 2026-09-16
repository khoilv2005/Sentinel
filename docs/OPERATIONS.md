# SentinelView Operations Guide

## Start

```bash
docker compose up -d --build
```

## Status

```bash
docker compose ps
```

Expected core services:

```text
postgres
control-api
discovery-worker
collector-worker
notification-worker
web-ui
prometheus
snmp-exporter
blackbox-exporter
grafana
```

Loki starts only when its Compose profile is enabled.

## Logs

```bash
docker compose logs -f --tail=200
docker compose logs -f control-api
docker compose logs -f discovery-worker
docker compose logs -f collector-worker
docker compose logs -f notification-worker
docker compose logs -f web-ui
```

## Health checks

```text
UI               http://localhost:3001
Control health   http://localhost:8080/healthz
Control ready    http://localhost:8080/readyz
Prometheus       http://localhost:9090/-/healthy
Grafana          http://localhost:3000/api/health
```

## Back up PostgreSQL

Example:

```bash
docker compose exec -T postgres \
  pg_dump -U sentinel -d sentinel > sentinel-backup.sql
```

Restore into an empty lab database with `psql` as appropriate.

## Preserve vs destroy state

Preserve:

```bash
docker compose down
```

Destroy volumes:

```bash
docker compose down -v
```

Do not use `-v` merely to apply a credential/configuration change.

## Prometheus target troubleshooting

Open `http://localhost:9090/targets`.

Managed agents are not directly scraped. Their metrics appear under the `sentinel-control` scrape because agents push to the Control API first. Remote collector telemetry is also republished from the central Control API metrics endpoint.

Prometheus no longer owns a second set of SentinelView alert thresholds. Monitoring Rules in the Control API are the alert source of truth; Prometheus stores/querys time-series history and remains available to Grafana.

## Discovery troubleshooting

```bash
docker compose logs -f discovery-worker
```

Discovery is inventory-only in v0.4. It records observed Assets and identity metadata but does not mark an Asset down simply because a later scan receives no response. Operational health comes from configured monitoring methods.

Docker Desktop networking can limit L2 information such as MAC discovery compared with running collectors directly on the management network.

## Remote collector troubleshooting

```bash
docker compose logs -f collector-worker
```

Open **Monitoring -> Remote collectors** and inspect:

```text
last_poll_at
last_success_at
last_error
consecutive_failures
```

A remote monitoring assignment is considered unavailable after three consecutive failures. Overall Asset health is derived from all configured monitoring methods:

```text
UP        at least one healthy method and no failed method
DEGRADED  healthy and failed methods exist together
DOWN      configured methods are failed with no healthy method
UNKNOWN   no usable monitoring result yet
```

A successful poll resets the assignment failure count and clears `last_error`. One failed collector no longer overwrites data or health supplied by another active method.

For WinRM, verify that the target allows the selected transport and that the supplied account may query CIM. For SSH, verify the account and host-key policy. For SNMP, verify v2c/v3 credentials and device ACLs.

## Monitoring telemetry storage

Remote telemetry is stored per monitoring assignment in `monitoring_telemetry_latest`. SentinelView maintains `agentless_telemetry_latest` only as a compatibility aggregate for the current Prometheus/UI layer while v0.4 migration is in progress.

This prevents an SNMP poll with partial fields from erasing CPU/RAM/disk data previously collected by SSH or WinRM on the same Asset.

## Notification troubleshooting

```bash
docker compose logs -f notification-worker
```

Open **Alerts -> Notifications** to inspect recent delivery state and use **Test** for a real delivery attempt.

Delivery states include:

```text
pending
sent
suppressed
failed
```

Pending failures use bounded exponential retry. `last_error` records the most recent delivery error without exposing the stored channel secret through the API.

Channel delivery configuration is encrypted using `SENTINEL_CREDENTIAL_SECRET`. Keep that value stable. Changing it without deliberate credential rotation makes existing remote-monitoring and notification credentials undecryptable.

## Maintenance troubleshooting

Maintenance matching supports:

- a specific `device_id`;
- a `site`;
- global windows when neither is supplied.

If **Suppress problem notifications** is enabled, matching active problem transitions are stored as suppressed instead of being sent. If **Exclude from SLA accounting** is enabled, overlapping maintenance time is removed from the availability denominator.

Use an explicit start/end window; recurrence rules are not yet implemented.

## UI session troubleshooting

If the browser returns to the login screen, the signed session expired, the local account was disabled/deleted, or authentication state became invalid. Sign in again after resolving the account issue.

Role changes apply to already-issued bearer sessions because SentinelView reloads the current local-user role on authenticated requests.

If you changed `SENTINEL_ADMIN_PASSWORD` after the first database start, the existing user is not automatically overwritten. Use the Access page or intentionally recreate the lab database.

## Grafana persistent admin password

Grafana stores the initialized administrator credential inside `grafana-data`. Editing `GF_SECURITY_ADMIN_PASSWORD` later does not rotate that existing password.

On Windows, explicitly reset it with:

```powershell
.\scripts\reset-grafana-admin.ps1 -Password 'new-password'
```

Equivalent direct command:

```bash
docker compose exec -T grafana grafana cli admin reset-admin-password 'new-password'
```

This preserves dashboards and other persistent Grafana state.

## Clean-install database credentials

When creating `.env` from `.env.example`, keep the password embedded in `SENTINEL_DB_URL` aligned with `POSTGRES_PASSWORD`. The checked-in template starts with matching placeholder values to avoid a first-boot authentication mismatch.

## Upgrade procedure

1. Back up PostgreSQL.
2. Keep a copy of `.env` and especially the stable credential/session secrets.
3. Pull/extract the new SentinelView release.
4. Move/copy your `.env` into the release directory.
5. Rename `SENTINEL_AGENTLESS_WORKERS` to `SENTINEL_COLLECTOR_WORKERS` when convenient. The old variable is still accepted as a compatibility fallback during v0.4 migration.
6. Run `docker compose up -d --build`.
7. Verify UI login, Assets, collector worker, notification worker, managed agents and Prometheus targets.
8. Inspect notification delivery and maintenance/SLA behavior if those features are in use.

Until formal migrations are introduced, review release notes before upgrades that change existing table columns.
