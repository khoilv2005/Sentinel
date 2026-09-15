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

## Prometheus target troubleshooting

Open `http://localhost:9090/targets`.

Managed v0.3.0 agents are not directly scraped. Their metrics appear under the `sentinel-control` scrape because agents push to the Control API first.

## Discovery troubleshooting

```bash
docker compose logs -f discovery-worker
```

Docker Desktop networking can limit L2 information such as MAC discovery compared with running collectors directly on the management network.

## UI session troubleshooting

If the browser returns to the login screen, the signed session expired or became invalid. Sign in again.

If you changed `SENTINEL_ADMIN_PASSWORD` after the first database start, the existing user is not automatically overwritten. Use the Users page or intentionally recreate the lab database.

## Upgrade procedure

1. Back up PostgreSQL.
2. Keep a copy of `.env`.
3. Extract the new SentinelView release.
4. Move/copy your `.env` into the release directory.
5. Run `docker compose up -d --build`.
6. Verify UI login, hosts, agents and Prometheus targets.

Until formal migrations are introduced, review release notes before upgrades that change existing table columns.
