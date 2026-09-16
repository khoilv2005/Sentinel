# SentinelView API Overview

Interactive OpenAPI documentation:

```text
http://localhost:8080/docs
```

## Authentication

UI sessions:

```http
Authorization: Bearer <signed-ui-session>
```

Automation:

```http
X-API-Key: <SENTINEL_API_KEY>
```

Managed agents use their own bearer credential only for agent check-in/telemetry endpoints.

## Major endpoint groups

### Authentication

```text
POST /api/v1/auth/login
GET  /api/v1/auth/me
```

### Dashboard / Assets

Canonical monitored-asset endpoints:

```text
GET /api/v1/ui/overview
GET /api/v1/assets
GET /api/v1/assets/{id}/overview
GET /api/v1/assets/{id}/metrics
GET /api/v1/services
GET /api/v1/problems
POST /api/v1/problems/{id}/ack
GET /api/v1/search
```

Older `/api/v1/hosts*` endpoints remain callable for compatibility but are hidden from OpenAPI. The first-party UI uses the canonical `/assets` aliases.

### Asset inventory / discovery

```text
GET/POST /api/v1/devices
GET/PATCH/DELETE /api/v1/devices/{id}
POST /api/v1/discovery/scans
GET  /api/v1/discovery/scans
GET  /api/v1/discovery/scans/{id}
```

`Device` remains the canonical inventory record during the v0.4 compatibility transition. Discovery only enriches asset identity/inventory; runtime health belongs to configured monitoring methods.

### Monitoring assignments

```text
GET  /api/v1/monitoring/candidates
GET  /api/v1/monitoring/assignments
POST /api/v1/monitoring/assignments/bulk
POST /api/v1/monitoring/test
POST /api/v1/monitoring/assignments/{id}/poll
DELETE /api/v1/monitoring/assignments/{id}
```

Methods currently supported by remote assignments:

```text
winrm
ssh
snmp
```

Legacy `/api/v1/agentless/*` routes remain compatibility aliases in v0.4 but are hidden from OpenAPI.

### Monitoring credentials

```text
GET    /api/v1/credentials
POST   /api/v1/credentials
DELETE /api/v1/credentials/{id}
```

Secrets are encrypted at rest and are never returned by the API.

### Managed Agent

```text
GET/POST /api/v1/agent-policies
PATCH    /api/v1/agent-policies/{id}
POST     /api/v1/agents/enrollment-tokens
GET      /api/v1/agents/enrollment-tokens
POST     /api/v1/agents/enroll
POST     /api/v1/agents/checkin
POST     /api/v1/agents/telemetry
GET      /api/v1/agents
POST     /api/v1/agents/{id}/revoke
```

Managed Agent is one Monitoring method, not a prerequisite for asset monitoring.

### Alerting / operations

```text
GET/POST     /api/v1/rules
PATCH/DELETE /api/v1/rules/{id}
GET          /api/v1/events
GET/POST     /api/v1/topology
GET          /api/v1/topology/graph
GET/POST     /api/v1/notification-channels
GET          /api/v1/notification-deliveries
GET/POST     /api/v1/maintenance
```

SentinelView Control API is the single alert evaluator:

```text
Telemetry -> Rules -> Services -> Problems -> Notifications
```

Prometheus alert thresholds are not a second source of truth.

### Platform / reporting

```text
GET/POST /api/v1/slas
GET      /api/v1/availability
GET      /api/v1/audit
GET      /api/v1/users
POST     /api/v1/users
PATCH    /api/v1/users/{id}
GET      /api/v1/platform/settings
GET      /api/v1/integrations
```

`/api/v1/integrations` is treated as a capability catalog shown under Settings, not a separate operator workflow.

### Prometheus service discovery

```text
GET /api/v1/targets/prometheus
GET /api/v1/targets/snmp
GET /api/v1/targets/blackbox
```

These endpoints are backend service-discovery interfaces consumed by Prometheus/exporters. They are intentionally separate from operator-facing Monitoring configuration.

## Route hygiene

The v0.4 entrypoint keeps legacy implementation code isolated while duplicate route registrations are removed at import time. Regression tests ensure each HTTP method/path pair is unique and that notification/maintenance requests resolve to the modular encrypted/maintenance-aware implementations.
