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

## Monitoring architecture

The operator-facing workflow is:

```text
Assets -> Monitoring -> Services/Problems -> Notifications -> SLA
```

Discovery and Monitoring have different responsibilities:

- **Discovery** enriches asset inventory and scan history. It does not mark an asset up/down.
- **Monitoring** collects runtime evidence with Managed Agent, WinRM, SSH, SNMP and/or ICMP.

Prometheus is the time-series/history backend. SentinelView Control API is the single source of truth for alert thresholds and problem lifecycle.

## Prometheus target troubleshooting

Open `http://localhost:9090/targets`.

Managed agents are not directly scraped. Their metrics appear under the `sentinel-control` scrape because agents push to the Control API first. Remote WinRM/SSH/SNMP telemetry is also republished from the central Control API metrics endpoint.

## Discovery troubleshooting

```bash
docker compose logs -f discovery-worker
```

Open **Monitor -> Assets -> Discovery**.

Docker Desktop networking can limit L2 information such as MAC discovery compared with running collectors directly on the management network.

A discovery miss is not a health failure. If an asset is expected to be continuously monitored, configure a Monitoring method.

## Remote monitoring troubleshooting

```bash
docker compose logs -f collector-worker
```

Open **Configure -> Monitoring -> Remote methods** and inspect:

```text
last_poll_at
last_success_at
last_error
consecutive_failures
```

WinRM, SSH and SNMP assignments keep independent latest samples. One failed method does not mark the whole asset down while another enabled method remains healthy. The asset transitions down only when all enabled remote methods have reached the failure threshold and no managed Sentinel Agent is online.

For WinRM, verify that the target allows the selected transport and that the supplied account may query CIM. For SSH, verify the account and host-key policy. For SNMP, verify v2c/v3 credentials and device ACLs.

Legacy note: the Python module and database table still use `agentless_*` names during the v0.4 compatibility transition. The Docker service and UI use the unified Monitoring terminology.

## Notification troubleshooting

```bash
docker compose logs -f notification-worker
```

Open **Configure -> Alerts -> Notifications** to inspect recent delivery state and use **Test** for a real delivery attempt.

Delivery states include:

```text
pending
sent
suppressed
failed
```

Pending failures use bounded exponential retry. `last_error` records the most recent delivery error without exposing the stored channel secret through the API.

Channel delivery configuration is encrypted using `SENTINEL_CREDENTIAL_SECRET`. Keep that value stable. Changing it without deliberate credential rotation makes existing monitoring and notification credentials undecryptable.

## Maintenance troubleshooting

Open **Configure -> Alerts -> Maintenance**.

Maintenance matching supports:

- a specific `device_id`;
- a `site`;
- global windows when neither is supplied.

If **Suppress problem notifications** is enabled, matching active problem transitions are stored as suppressed instead of being sent. If **Exclude from SLA accounting** is enabled, overlapping maintenance time is removed from the availability denominator.

Use an explicit start/end window; recurrence rules are not yet implemented.

## UI session troubleshooting

If the browser returns to the login screen, the signed session expired, the local account was disabled/deleted, or authentication state became invalid. Sign in again after resolving the account issue.

Role changes apply to already-issued bearer sessions because SentinelView reloads the current local-user role on authenticated requests.

If you changed `SENTINEL_ADMIN_PASSWORD` after the first database start, the existing user is not automatically overwritten. Use **Platform -> Access** or intentionally recreate the lab database.

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
5. Run `docker compose down` so the old `agentless-worker` service is removed cleanly during the v0.4 rename.
6. Run `docker compose up -d --build`.
7. Verify UI login, Assets, `collector-worker`, `notification-worker`, managed agents and Prometheus targets.
8. Inspect notification delivery and maintenance/SLA behavior if those features are in use.

Do not use `docker compose down -v` for this rename. Persistent PostgreSQL, Prometheus and Grafana volumes are compatible and should be preserved.

Until formal migrations are introduced, review release notes before upgrades that change existing table columns.
