# SentinelView v0.4 API Overview

Interactive OpenAPI documentation: `http://localhost:8080/docs`

## Authentication

UI sessions use `Authorization: Bearer <signed-ui-session>`. Automation uses `X-API-Key`. Managed agents use their own bearer credential for check-in/telemetry.

## First-party UI

```text
GET /api/v1/ui/overview
GET /api/v1/hosts
GET /api/v1/hosts/{id}/overview
GET /api/v1/hosts/{id}/metrics
GET /api/v1/services
GET /api/v1/problems
POST /api/v1/problems/{id}/ack
GET /api/v1/search
```

## Assets / discovery

```text
GET/POST /api/v1/devices
GET/PATCH/DELETE /api/v1/devices/{id}
POST /api/v1/discovery/scans
GET  /api/v1/discovery/scans
GET  /api/v1/discovery/scans/{id}
```

Discovery is inventory-only: it may create/enrich Assets and observation history, but it does not own operational up/down health.

## Monitoring assignments

```text
GET    /api/v1/monitoring/candidates
GET    /api/v1/monitoring/assignments
POST   /api/v1/monitoring/assignments/bulk
DELETE /api/v1/monitoring/assignments/{id}
POST   /api/v1/monitoring/assignments/{id}/poll
POST   /api/v1/monitoring/test
```

Remote methods currently include WinRM, SSH and SNMP. Assignment requires the target to exist as an Asset first. The v0.3 `/api/v1/agentless/*` endpoints remain temporarily and are deprecated in OpenAPI.

## Credentials

```text
GET    /api/v1/credentials
POST   /api/v1/credentials
DELETE /api/v1/credentials/{id}
```

## Managed agents

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

## Monitoring / configuration

```text
GET/POST /api/v1/rules
PATCH/DELETE /api/v1/rules/{id}
GET       /api/v1/events
GET/POST  /api/v1/topology
GET       /api/v1/topology/graph
GET       /api/v1/integrations
```

## Platform / reporting

```text
GET/POST /api/v1/notification-channels
GET/POST /api/v1/maintenance
GET/POST /api/v1/slas
GET      /api/v1/availability
GET      /api/v1/audit
GET      /api/v1/users
POST     /api/v1/users
PATCH    /api/v1/users/{id}
GET      /api/v1/platform/settings
```

## Prometheus service discovery

```text
GET /api/v1/targets/prometheus
GET /api/v1/targets/snmp
GET /api/v1/targets/blackbox
```
