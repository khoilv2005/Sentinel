# SentinelView v0.3.0 Project Status

## Release objective

v0.3.0 converts SentinelView from a monitoring backend with a small scan UI into a platform with a first-party operations console and supports both agentless and optional managed-agent monitoring.

## Implemented and tested

### First-party UI

- Login/session flow.
- Overview dashboard.
- Hosts and Host Detail.
- Service-centric monitoring.
- Active Problems, suppression state and acknowledgement.
- Events.
- Network Discovery.
- Inventory.
- Managed Agents.
- Agentless WinRM/SSH/SNMP monitoring.
- Agentless `/24` candidate listing and selected/discovered/entire-CIDR assignment.
- Encrypted credential profiles.
- Agent Policies.
- Monitoring Rules.
- Topology visualization.
- SNMP targets.
- Integration catalog.
- Notification channel configuration, channel test and delivery-status view.
- Maintenance windows with problem-notification suppression and SLA exclusion.
- Availability/SLA views.
- Users & Roles.
- Audit Log.
- Global search.
- Settings/advanced component links.

### Control plane

- Local PBKDF2 users.
- Signed UI bearer sessions with current account enabled/role state revalidated from PostgreSQL.
- Existing API-key automation compatibility.
- Derived services from managed-agent or agentless telemetry.
- Persistent problem lifecycle.
- Problem acknowledgement and maintenance suppression.
- Rule editing with duplicate-metric bootstrap regression protection.
- Policy editing/versioning.
- Audit events.
- Maintenance/SLA/channel models.
- Maintenance-aware availability and SLA denominator exclusion.
- Persistent notification delivery queue.
- Automatic problem open/escalation/recovery/post-maintenance notification transitions.
- Webhook, Slack, Teams, Telegram and SMTP delivery.
- Bounded notification retry/backoff.
- Encrypted notification delivery configuration with redacted API responses.
- Prometheus history proxy for host charts.
- Availability calculation from state-change events.

### Collection and workers

- private CIDR discovery;
- PostgreSQL inventory;
- outbound managed-agent enrollment;
- per-agent credentials;
- Windows Service/Linux systemd agent install;
- managed-agent CPU/RAM/disk/network/uptime/process telemetry;
- WinRM/CIM agentless Windows collection;
- SSH agentless Linux/Unix collection;
- generic SNMP agentless collection;
- agentless three-failure down transition and successful recovery reset;
- Prometheus metrics;
- notification delivery worker;
- Grafana dashboards;
- SNMP exporter and blackbox exporter integration;
- Docker Compose packaging.

## Automated QA

The repository runs two complementary GitHub workflows.

### Core CI

- Python API/unit/regression tests.
- Go 1.25 module verification, unit tests and Linux/Windows cross-builds.
- JavaScript syntax checks including the runtime operations enhancement module.
- configuration validation.

### Disposable integration CI

- clean no-cache Docker application build;
- real OpenSSH target collection;
- real SNMP daemon collection;
- agentless failure hysteresis and successful recovery;
- real local WinRM/CIM collection on a disposable Windows runner.

The CI strategy intentionally supplies disposable external conditions that are not guaranteed to exist on a developer laptop. A developer therefore does not need host-installed Go, a permanent Windows WinRM VM, SSH server or SNMP appliance to validate those code paths.

## Current limitations

v0.3.0 does not claim:

- a commercial-scale vendor plugin catalog;
- full automatic LLDP/CDP topology discovery;
- enterprise notification policy trees, on-call calendars and multi-stage escalation;
- recurring maintenance recurrence rules beyond explicit start/end windows;
- OIDC/LDAP/SAML;
- fine-grained object-level RBAC;
- remote collectors/distributed monitoring;
- HA;
- historical SLA data before state-transition recording began;
- MSI/DEB/RPM release packages;
- signed staged automatic agent updates.

These remain explicit roadmap work rather than UI-only placeholders presented as completed features.
