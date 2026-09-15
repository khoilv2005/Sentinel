# SentinelView v0.3.0 Project Status

## Release objective

v0.3.0 converts SentinelView from a monitoring backend with a small scan UI into a platform with a first-party operations console.

## Implemented and tested

### First-party UI

- Login/session flow.
- Overview dashboard.
- Hosts and Host Detail.
- Service-centric monitoring.
- Active Problems and acknowledgement.
- Events.
- Network Discovery.
- Inventory.
- Managed Agents.
- Agent Policies.
- Monitoring Rules.
- Topology visualization.
- SNMP targets.
- Integration catalog.
- Notification channel configuration.
- Maintenance windows.
- Availability/SLA views.
- Users & Roles.
- Audit Log.
- Global search.
- Settings/advanced component links.

### Control plane

- Local PBKDF2 users.
- Signed UI bearer sessions.
- Existing API-key automation compatibility.
- Derived services from latest telemetry.
- Persistent problem lifecycle.
- Problem acknowledgement.
- Rule editing.
- Policy editing/versioning.
- Audit events.
- Maintenance/SLA/channel models.
- Prometheus history proxy for host charts.
- Availability calculation from state-change events.

### Existing v0.2.3 capabilities retained

- private CIDR discovery;
- PostgreSQL inventory;
- outbound managed-agent enrollment;
- per-agent credentials;
- Windows Service/Linux systemd agent install;
- CPU/RAM/disk/network/uptime/process telemetry;
- Prometheus metrics;
- Grafana dashboards;
- SNMP exporter and blackbox exporter integration;
- Docker Compose packaging.

## Automated QA in the build environment

- Python API/unit/integration tests: 12 passing.
- Python bytecode compilation: passing.
- JavaScript syntax checks: passing.
- Docker Compose YAML parse: passing.
- Grafana JSON and deployment YAML validation: included in release validation.

The build environment does not provide a Docker daemon and cannot reliably download Go modules, so the final real Docker/Go cross-build must run on a normal Docker host with Internet access. CI and Dockerfiles perform that build with Go 1.25.

## Honest limitations

v0.3.0 does not yet implement:

- a commercial-scale vendor plugin catalog;
- full automatic LLDP/CDP topology discovery;
- real production notification routing/dispatch;
- OIDC/LDAP/SAML;
- fine-grained object-level RBAC;
- remote collectors/distributed monitoring;
- HA;
- full historical SLA data before v0.3.0;
- MSI/DEB/RPM release packages;
- signed staged automatic agent updates.

These remain explicit roadmap work.
