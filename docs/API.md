# SentinelView v0.3.0 API Overview

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

### First-party UI

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

### Inventory/discovery

```text
GET/POST /api/v1/devices
GET/PATCH/DELETE /api/v1/devices/{id}
POST /api/v1/discovery/scans
GET  /api/v1/discovery/scans
GET  /api/v1/discovery/scans/{id}
```

### Managed agents

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

### Monitoring/configuration

```text
GET/POST /api/v1/rules
PATCH/DELETE /api/v1/rules/{id}
GET       /api/v1/events
GET/POST  /api/v1/topology
GET       /api/v1/topology/graph
GET       /api/v1/integrations
```

### Platform/reporting

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

### Prometheus service discovery

```text
GET /api/v1/targets/prometheus
GET /api/v1/targets/snmp
GET /api/v1/targets/blackbox
```

These endpoints are consumed by Prometheus/collectors and are intentionally separate from normal UI endpoints.
