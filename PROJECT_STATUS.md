# SentinelView v0.4 consolidation status

## Objective

v0.4 simplifies SentinelView around a single operator model instead of exposing every implementation component as a separate product feature.

```text
Asset
  -> Monitoring methods
  -> Services
  -> Problems
  -> Notifications
  -> SLA
```

The detailed migration design is documented in `docs/ARCHITECTURE_V04.md`.

## Consolidated product surface

### Monitor

- **Dashboard** — top-level infrastructure health.
- **Assets** — all infrastructure Assets, with Services, Topology, Discover and Inventory-detail tabs.
- **Problems** — active warning/critical/suppressed conditions and acknowledgement.
- **Operational Events** — discovery observations, collection state changes and runtime history.

### Configure / manage

- **Monitoring** — Managed Agent, Remote collectors, Credentials and Agent settings.
- **Alerts** — Rules, Notifications and Maintenance.

### Report

- **Availability & SLA**.

### Platform

- **Access**.
- **Audit**.
- **Settings / Capabilities**.

Legacy component routes remain temporarily reachable while data/API migration is completed, but they are no longer presented as independent top-level products.

## Completed consolidation work

### Asset boundary

- `Device` is the current Asset source of truth.
- Discovery is inventory-only and no longer marks Assets operationally UP/DOWN.
- A remote monitoring assignment can only target an Asset that already exists.
- `/24` assignment no longer creates placeholder Devices merely because addresses exist in the subnet.
- New `/api/v1/monitoring/*` endpoints provide product-neutral terminology.
- Legacy `/api/v1/agentless/*` endpoints remain temporarily and are deprecated in OpenAPI.

### Monitoring health

Overall Asset health is derived from all configured monitoring methods:

```text
UP
DEGRADED
DOWN
UNKNOWN
```

One failed method alongside a healthy method produces `DEGRADED` rather than allowing the last worker to overwrite the Asset to `DOWN`.

Each configured remote method is exposed as its own Service (for example SSH monitoring or SNMP monitoring).

### Telemetry isolation

Remote latest telemetry is now stored per monitoring assignment in `monitoring_telemetry_latest`.

The v0.3 device-level `agentless_telemetry_latest` row is maintained only as a compatibility aggregate for existing Prometheus/UI code. This prevents one collector with partial data from erasing telemetry produced by another method on the same Asset.

### Collector terminology

The Compose service is now `collector-worker` and uses `SENTINEL_COLLECTOR_WORKERS`.

`SENTINEL_AGENTLESS_WORKERS` remains a compatibility environment fallback while v0.4 migration is in progress.

### Alert source of truth

SentinelView database-backed Monitoring Rules -> Services -> Problems are the product alert source of truth.

The checked-in Prometheus alert rule file is intentionally empty. Prometheus remains the time-series/history backend rather than a parallel alert engine with conflicting thresholds.

### SNMP consolidation

Direct SNMP collection is represented as a Monitoring Assignment.

A SNMP credential can optionally provide:

```json
{
  "exporter_auth": "public_v2",
  "exporter_module": "if_mib"
}
```

for additional `snmp_exporter` collection without exposing secrets through Prometheus HTTP service discovery.

Legacy `Device.snmp_*` targets remain as a temporary compatibility fallback and the old SNMP page is demoted to **Settings -> Legacy SNMP exporter**.

## Existing platform capabilities retained

- local users and role enforcement;
- signed UI sessions and API-key automation compatibility;
- managed-agent enrollment/check-in/telemetry;
- WinRM, SSH and SNMP remote collectors;
- monitoring rules, Services and persistent Problems;
- problem acknowledgement;
- notification dispatch through webhook, Slack, Teams, Telegram and SMTP;
- maintenance suppression and SLA exclusion;
- topology;
- Prometheus history and Grafana dashboards;
- audit log;
- global search;
- Docker Compose packaging.

## Automated QA

Core CI covers:

- Python API/unit/regression tests;
- Go module verification, unit tests and Linux/Windows cross-builds;
- JavaScript syntax/configuration validation.

Disposable integration CI covers:

- clean no-cache Docker application build;
- real OpenSSH collection;
- real SNMP daemon collection;
- remote-monitor failure/recovery behavior;
- real local WinRM/CIM collection on a Windows runner.

The v0.4 branch adds regressions for:

- discovery not overriding operational health;
- inventory-first monitoring assignments;
- multi-method telemetry isolation;
- `DEGRADED` health derivation;
- SNMP exporter targets derived from the monitoring model.

## Remaining v0.4 migration work

- remove legacy `AgentlessMonitor` / `agentless_*` naming at the database/module level after compatibility migration;
- migrate/remove remaining `Device.agent_*` and `Device.snmp_*` compatibility fields;
- remove old top-level component route implementations after all UI/API callers use consolidated domains;
- complete one canonical SNMP profile/configuration model;
- surface `DEGRADED` explicitly in every dashboard/report count;
- replace compatibility telemetry aggregation when all Prometheus/UI readers can consume assignment-aware data directly;
- remove deprecated `/api/v1/agentless/*` routes in a later breaking release.

## Product limitations not addressed by consolidation

SentinelView still does not claim:

- a commercial-scale vendor plugin catalog;
- automatic LLDP/CDP topology discovery;
- enterprise notification policy trees/on-call calendars;
- recurring maintenance rules beyond explicit start/end windows;
- OIDC/LDAP/SAML;
- fine-grained object-level RBAC;
- remote distributed collectors or HA;
- historical SLA data before state-transition recording began;
- MSI/DEB/RPM release packages;
- signed staged automatic agent updates.
