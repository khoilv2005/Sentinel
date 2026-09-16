# SentinelView unified monitoring architecture

This document defines the product and backend boundaries introduced by the v0.4 consolidation work.

## Product model

SentinelView has six primary domains:

1. **Assets** — what infrastructure objects exist?
2. **Collection** — how is data collected from each asset?
3. **Monitoring** — what is the current health/service state?
4. **Alerting** — what problems exist and who should be notified?
5. **Reporting** — what availability/SLA has been achieved?
6. **Platform** — who can access or change the system?

These domains replace older top-level product concepts such as separate Hosts, Inventory, Agentless and SNMP pages.

## UI navigation

Primary navigation is intentionally small:

```text
MONITOR
├── Dashboard
├── Assets
├── Problems
└── Operational Events

CONFIGURE
├── Monitoring
└── Alerts

REPORT
└── Availability & SLA

PLATFORM
├── Access
├── Audit
└── Settings
```

Sub-views remain available without becoming separate product areas:

- Assets: All assets, Services, Topology, Discovery.
- Monitoring: Remote methods, Managed Agent, Credentials, Agent settings.
- Alerts: Rules, Notifications, Maintenance.

## Asset boundary

`Device` remains the canonical asset/inventory identity during the v0.4 transition.

Discovery is an inventory function. It may update identity metadata such as hostname, MAC address, latency, open ports, class, site and last observation time. It must not force operational health to `up` or `down`.

An explicit Add/Monitor operation may create an asset intentionally, but the new asset starts `unknown` until monitoring returns evidence.

## Monitoring methods

An asset may be monitored through one or more methods:

```text
Managed Agent
WinRM
SSH
SNMP
ICMP / blackbox
```

The operator should choose methods based on the asset, not choose a separate product area.

Examples:

```text
Windows server: Managed Agent OR WinRM, optionally ICMP
Linux server:   Managed Agent OR SSH, optionally ICMP
Switch/router:  SNMP + ICMP
UPS:            SNMP + ICMP
```

## Remote monitoring assignments

The database table currently named `agentless_monitors` remains for migration compatibility. Operator/API terminology is **monitoring assignment**.

New API names:

```text
GET  /api/v1/monitoring/candidates
GET  /api/v1/monitoring/assignments
POST /api/v1/monitoring/assignments/bulk
POST /api/v1/monitoring/test
POST /api/v1/monitoring/assignments/{id}/poll
DELETE /api/v1/monitoring/assignments/{id}
```

Legacy `/api/v1/agentless/*` routes remain hidden compatibility aliases in v0.4.

## Per-assignment telemetry

The old `agentless_telemetry_latest` table is keyed only by `device_id`. Multiple methods on one asset therefore competed for the same row.

v0.4 adds:

```text
collector_telemetry_latest
```

Primary key:

```text
monitor_id
```

Each WinRM/SSH/SNMP assignment now keeps an independent latest observation.

The old device-level table remains as a compatibility aggregate for existing Host Detail and Prometheus metric export. Rich endpoint sources (WinRM/SSH) outrank generic SNMP unless they become stale.

## Health aggregation

One failed collector must not mark the whole asset down while another configured method is healthy.

Current transition rule:

- an online Managed Agent is positive evidence that the asset is up;
- any healthy remote assignment is positive evidence that the asset is up;
- the asset is down only when every enabled remote assignment has reached the configured three-failure threshold and no Managed Agent is online;
- an asset without monitoring evidence remains unknown.

Service-level degradation is represented through Services and Problems. The UI may present an asset as `degraded` when reachability is up but one or more monitored services are unhealthy.

## Alerting source of truth

SentinelView Control API is the single alert evaluator:

```text
Telemetry
  -> Monitoring Rules
  -> Services
  -> Problems
  -> Notifications
```

Prometheus stores time-series history and serves Grafana/history queries. Prometheus alert rules are intentionally empty to prevent threshold drift and duplicate alert engines.

## SNMP boundary

SNMP is one Monitoring method. The user should not have to decide between a separate `SNMP` product page and `Agentless -> SNMP`.

`snmp_exporter` may continue to exist internally for Prometheus-native vendor modules, but this is a backend implementation detail. Vendor packs such as APC/Vertiv should appear as monitoring profiles, not new top-level navigation items.

## Event versus audit

These concepts remain separate:

- **Operational Events** — discovery observations, collector polls and runtime state transitions.
- **Audit** — who changed configuration, access, rules or monitoring assignments.

## Migration compatibility

v0.4 intentionally avoids a destructive schema migration. Existing tables and legacy endpoints remain readable while new boundaries are introduced.

A future schema migration may rename `AgentlessMonitor` to `MonitorAssignment` and remove legacy `Device.agent_*` / `Device.snmp_*` compatibility fields after all consumers have moved to the unified model.
