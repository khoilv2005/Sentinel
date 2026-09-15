# SentinelView Architecture — v0.3.0

## Product boundary

SentinelView is split into four planes:

1. **Operations UI** — the primary day-to-day interface.
2. **Control plane** — inventory, configuration, agent enrollment, problems and events.
3. **Telemetry plane** — Prometheus-compatible metrics plus SNMP/blackbox collectors.
4. **Advanced analytics** — Grafana dashboards for deep analysis rather than normal administration.

```text
Browser
  |
  v
web-ui (Nginx, :3001)
  |
  v
control-api (FastAPI, :8080)
  |       |            |
  |       |            +--> agent artifacts
  |       +--> Prometheus API for history
  +--> PostgreSQL
        inventory/config/events/problems/users

Managed endpoint agent ----outbound----> control-api
Network device ----------SNMP----------> snmp_exporter -> Prometheus
Any inventoried device --probe---------> blackbox_exporter -> Prometheus
control-api /metrics ------------------> Prometheus -> Grafana
```

## First-party UI

The UI is a dependency-light modular JavaScript SPA served by Nginx. It uses the Control API as the only application backend. The browser does not query PostgreSQL or Prometheus directly.

Why this matters:

- RBAC/session checks stay centralized.
- PromQL is not exposed as the main UX.
- Backend implementations can change without rewriting every UI view.
- Grafana can remain optional for normal operators.

## Authentication

UI login flow:

```text
POST /api/v1/auth/login
        |
        v
PBKDF2 password verification
        |
        v
HMAC-signed session token
        |
        v
Authorization: Bearer <session>
```

External automation keeps API-key compatibility through `X-API-Key`.

Roles in v0.3.0:

- `admin`
- `operator`
- `viewer`

OIDC/LDAP/SAML are not yet implemented.

## Managed agent

The default agent data path is outbound:

```text
Agent -> enroll -> unique credential -> check-in/telemetry -> Control API
```

The endpoint does not need to expose a Prometheus scrape port to the monitoring server.

Latest telemetry is stored in PostgreSQL for the first-party UI. Prometheus scrapes SentinelView's central `/metrics` endpoint for historical time-series storage.

## Service-state engine

v0.3.0 derives service checks from current inventory and managed-agent telemetry:

- Host availability
- Sentinel Agent
- CPU utilization
- Memory utilization
- Disk per mount point
- Process count
- Network interface collector presence

Monitoring rules determine warning/critical thresholds for CPU, memory, disk and agent availability. Active non-OK services are persisted as `problems`.

## Problem lifecycle

```text
OK
 |
 +-- threshold/availability violation --> OPEN
                                      |
                                      +--> ACKNOWLEDGED
                                      |
                                      +-- condition clears --> RESOLVED
```

The current problem engine uses latest telemetry. Prometheus rules still exist for Prometheus-native alerts, but first-party UI problems are the main product state in v0.3.0.

## Discovery

Discovery jobs are created by the Control API and executed by `discovery-worker`.

```text
CIDR -> private-range validation -> worker -> ICMP/TCP probes -> inventory/events
```

The worker records state changes so v0.3.0 can begin availability accounting.

## SNMP

SNMP target data lives in device inventory. Prometheus uses HTTP service discovery from the Control API and passes targets to `snmp_exporter`.

The first-party UI configures the target metadata; `snmp_exporter` owns protocol collection.

## Persistence

PostgreSQL stores control-plane state. Prometheus stores metric history. Grafana stores only its own configuration/user state in its volume.

v0.3.0 adds tables without altering v0.2.3 managed-agent tables, which keeps this lab upgrade compatible with `create_all`. Alembic-style formal migrations remain future work.

## Scaling direction

The architecture intentionally separates control and telemetry paths so future releases can introduce:

- remote collectors per site;
- Prometheus remote write / Mimir;
- Redis/event bus;
- HA control API replicas;
- PostgreSQL HA;
- Loki logs;
- OpenTelemetry/Alloy ingestion;
- centralized agent update rollout.
