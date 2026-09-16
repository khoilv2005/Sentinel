# SentinelView Project Status — v0.4 consolidation

## Release objective

The v0.4 consolidation removes duplicate operator concepts without removing monitoring capability. SentinelView now presents one asset model, one monitoring workflow and one alerting workflow instead of exposing backend implementation components as separate product features.

The canonical product flow is:

```text
Assets -> Monitoring -> Services/Problems -> Notifications -> SLA
```

## Product domains

SentinelView is organized into six domains:

1. **Assets** — inventory, discovery, services and topology.
2. **Collection** — Managed Agent, WinRM, SSH, SNMP and ICMP/blackbox methods.
3. **Monitoring** — runtime state and derived services.
4. **Alerting** — rules, problems, notifications and maintenance.
5. **Reporting** — availability and SLA.
6. **Platform** — access, audit and settings.

## First-party UI

Primary navigation is intentionally reduced:

### Monitor

- Dashboard.
- Assets.
- Problems.
- Operational Events.

### Configure

- Monitoring.
- Alerts.

### Report

- Availability & SLA.

### Platform

- Access.
- Audit.
- Settings.

The following older top-level pages are now sub-views rather than separate product concepts:

- Hosts + Inventory -> Assets.
- Services + Topology + Discovery -> Asset sub-views.
- Agents + Agentless + Credentials + Agent Policies -> Monitoring sub-views.
- SNMP -> one Monitoring method rather than a separate product workflow.
- Monitoring Rules + Notifications + Maintenance -> Alerts sub-views.
- Integrations -> capability catalog under Settings.

Legacy hash routes remain available where needed for compatibility, but the primary sidebar no longer exposes them independently.

## Asset and discovery boundary

`Device` remains the canonical asset record during the compatibility transition.

Discovery now performs inventory discovery only:

- private-CIDR enumeration;
- hostname/MAC/open-port metadata;
- device-class enrichment;
- site assignment;
- discovery observation events.

Discovery no longer changes an asset from `up` to `down` (or `down` to `up`) merely because a scan does or does not receive a probe response. Runtime health belongs to configured monitoring methods.

## Monitoring

### Managed Agent

- outbound enrollment;
- per-agent credentials;
- Windows Service/Linux systemd installation;
- CPU/RAM/disk/network/uptime/process telemetry;
- centralized agent settings/policy;
- revoke/re-enroll lifecycle.

### Remote methods

- WinRM/CIM for Windows;
- SSH for Linux/Unix;
- generic SNMP;
- selected/discovered/entire-private-CIDR assignment;
- encrypted credential profiles;
- scheduled collection in `collector-worker`.

New operator/API terminology uses **monitoring assignment** rather than **agentless monitor**. Legacy `/api/v1/agentless/*` APIs remain compatibility aliases while new clients use `/api/v1/monitoring/*`.

## Per-assignment telemetry

v0.4 adds `collector_telemetry_latest`, keyed by `monitor_id`.

This fixes a structural problem in the older device-level `agentless_telemetry_latest` model: multiple methods on one asset no longer overwrite one another's latest sample.

The old table is maintained temporarily as a compatibility aggregate for Host Detail and Prometheus export. WinRM/SSH data is preferred over generic SNMP unless the richer source becomes stale.

## Health aggregation

- an online Managed Agent is positive `up` evidence;
- any healthy remote monitoring assignment is positive `up` evidence;
- failure of one method does not mark the whole asset down while another enabled method remains healthy;
- an asset transitions `down` only when every enabled remote assignment reaches the failure threshold and no Managed Agent is online;
- assets without runtime evidence remain `unknown`;
- service-level problems can make an otherwise reachable asset appear `degraded` in the UI.

## Alerting

SentinelView Control API is the single alerting source of truth:

```text
Telemetry
  -> Monitoring Rules
  -> Services
  -> Problems
  -> Notifications
```

Prometheus remains the time-series/history backend. Its Sentinel alert rule file is intentionally empty so Prometheus does not maintain competing alert thresholds.

Implemented alerting behavior includes:

- persistent Problem lifecycle;
- acknowledgement;
- maintenance suppression;
- open/escalation/recovery/post-maintenance notification transitions;
- webhook, Slack, Teams, Telegram and SMTP delivery;
- bounded retry/backoff;
- encrypted notification configuration;
- SLA maintenance exclusion.

## Workers and platform services

Core Docker services:

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

`snmp-exporter` and `blackbox-exporter` are backend collection components. They are not separate operator product areas.

## Automated QA

The repository runs two complementary GitHub workflows.

### Core CI

- Python API/unit/regression tests.
- unified-monitoring boundary tests.
- Go module verification, unit tests and Linux/Windows cross-builds.
- JavaScript syntax checks.
- configuration validation.

### Disposable integration CI

- clean no-cache Docker application build;
- real OpenSSH target collection;
- real SNMP daemon collection;
- failure hysteresis and successful recovery;
- real local WinRM/CIM collection on a disposable Windows runner.

## Compatibility notes

The v0.4 consolidation intentionally avoids a destructive database migration.

Temporary compatibility items include:

- table/class names containing `Agentless`;
- legacy `/api/v1/agentless/*` endpoint aliases;
- device-level aggregate telemetry used by existing Host Detail/Prometheus paths;
- existing `Device.agent_*` and `Device.snmp_*` fields.

These can be removed in a later schema-migration release after all consumers use the unified model.

## Current limitations

SentinelView does not claim:

- a commercial-scale vendor plugin catalog;
- full automatic LLDP/CDP topology discovery;
- enterprise notification policy trees, on-call calendars and multi-stage escalation;
- recurring maintenance recurrence rules beyond explicit start/end windows;
- OIDC/LDAP/SAML;
- fine-grained object-level RBAC;
- distributed remote collectors;
- HA;
- historical SLA data before state-transition recording began;
- MSI/DEB/RPM release packages;
- signed staged automatic agent updates.

These remain roadmap work rather than duplicate UI placeholders.
