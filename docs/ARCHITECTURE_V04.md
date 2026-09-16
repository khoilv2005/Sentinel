# SentinelView v0.4 architecture consolidation

## Goal

SentinelView v0.4 reduces feature duplication by organizing the product around operator workflows rather than implementation components.

```text
Asset
  -> Monitoring methods
      -> managed agent
      -> WinRM
      -> SSH
      -> SNMP
      -> reachability
  -> Services
  -> Problems
  -> Notifications
  -> SLA
```

## Product domains

1. **Assets** — what infrastructure exists?
2. **Collection** — how is telemetry collected?
3. **Monitoring** — what does current telemetry mean?
4. **Alerting** — what needs attention and who should be notified?
5. **Reporting** — what availability/SLA was achieved?
6. **Platform** — who can configure and operate the system?

## Single Asset source of truth

`Device` remains the v0.4 asset record while the schema is migrated incrementally.

Discovery, manual creation, managed-agent enrollment and future imports may add or enrich an Asset. Monitoring assignment must not create an Asset implicitly.

```text
Asset exists first
        ↓
Monitoring is assigned second
```

## Discovery boundary

Discovery is inventory-only. It may update IP/hostname/MAC identity, open ports, inferred device class, site, last observation time and discovery history.

Discovery must not set operational health to `up` or `down`. A host missing from a discovery scan is not automatically a monitoring outage. Operational health is owned by configured monitoring methods.

## Monitoring assignments

The v0.3 `AgentlessMonitor` model remains temporarily for database compatibility, but the product/API term is **Monitoring Assignment**.

```text
GET    /api/v1/monitoring/candidates
GET    /api/v1/monitoring/assignments
POST   /api/v1/monitoring/assignments/bulk
DELETE /api/v1/monitoring/assignments/{id}
POST   /api/v1/monitoring/assignments/{id}/poll
POST   /api/v1/monitoring/test
```

Legacy `/api/v1/agentless/*` routes remain during migration and are deprecated in OpenAPI.

## UI consolidation

The top-level navigation is reduced to workflow concepts:

```text
MONITOR
- Dashboard
- Assets
- Problems
- Operational Events

MANAGE / CONFIGURE
- Monitoring
- Alerts

REPORT
- Availability & SLA

PLATFORM
- Access
- Audit
- Settings
```

Legacy component pages remain as domain tabs during migration.

### Assets
- All assets
- Services
- Topology
- Discover
- Inventory details

### Monitoring
- Managed agent
- Remote collectors
- Credentials
- Agent settings
- SNMP exporter

### Alerts
- Rules
- Notifications
- Maintenance

### Settings
- Platform
- Capabilities

## Health ownership

Target health states are `UP`, `DEGRADED`, `DOWN`, and `UNKNOWN`. A later phase will derive overall asset health from monitoring-method/service state instead of allowing multiple workers to overwrite one `Device.state` field. Discovery stops writing operational state in phase 1.

## Telemetry migration

Current v0.3 storage has one `AgentlessTelemetryLatest` row per device, so multiple remote methods can overwrite one another. Phase 2 will introduce assignment-scoped telemetry:

```text
MonitorAssignment
  -> MonitorTelemetryLatest
```

## SNMP consolidation

Current v0.3 has both direct agentless SNMP polling and Prometheus `snmp_exporter` target configuration. They remain operational during phase 1, but only one product concept is exposed: **SNMP monitoring method**. A later phase will choose one canonical assignment/profile model.

## Alerting consolidation

SentinelView's database-backed Monitoring Rules are the intended product source of truth for Service/Problem state. Prometheus remains time-series/history storage. A later phase will remove duplicated Prometheus alert thresholds that can disagree with SentinelView rules.

## Migration phases

### Phase 1 — boundaries and navigation
- discovery becomes inventory-only;
- monitoring assignments require pre-existing Assets;
- new `/monitoring/*` API aliases;
- reduced top-level navigation;
- legacy component pages grouped behind domain tabs.

### Phase 2 — monitoring data model
- method-neutral assignment model;
- assignment-scoped latest telemetry;
- source precedence per metric;
- unified reachability method;
- overall health derivation.

### Phase 3 — SNMP and alerting cleanup
- one canonical SNMP configuration path;
- remove duplicate target/config fields from `Device`;
- one alert rule source of truth;
- Prometheus becomes metrics/history rather than a parallel alert engine.

### Phase 4 — legacy removal
- remove deprecated `/agentless/*` routes;
- remove obsolete component routes;
- migrate remaining `Device.agent_*` / `Device.snmp_*` compatibility fields;
- update release documentation.
