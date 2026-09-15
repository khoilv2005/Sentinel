# Changelog

## 0.3.0

### First-party operations UI

- Replaced the scan-only management experience with a complete SentinelView operations console.
- Added Overview, Hosts, Host Detail, Services, Problems, Events, Discovery, Inventory, Agents, Policies, Rules, Topology, SNMP, Integrations, Notifications, Maintenance, Availability/SLA, Users, Audit and Settings views.
- Added global host/event search and responsive sidebar layout.
- Added first-party SVG metric charts backed by Prometheus through the Control API.
- Grafana is now positioned as optional advanced analytics rather than the primary interface.

### Control plane

- Added local PBKDF2 user authentication and signed bearer sessions.
- Added admin/operator/viewer role foundation.
- Added derived service checks and persistent Problem lifecycle.
- Added problem acknowledgement.
- Added default monitoring rules for CPU, memory, disk and managed-agent availability.
- Added rule update/delete and agent policy update APIs.
- Added MaintenanceWindow, NotificationChannel, SlaDefinition, AuditEvent and LocalUser models.
- Added availability accounting based on v0.3.0 state-change events.
- Added Prometheus history proxy APIs for Host Detail.
- Added topology graph, integration catalog, global search and platform settings APIs.
- Discovery and agent transitions now record state-change events.

### Packaging and quality

- Updated release and managed agent version to 0.3.0.
- Updated Docker Compose image tags.
- Removed UI dependency on server-injected administrator API keys.
- Updated CI for the modular first-party UI.
- Expanded documentation for architecture, UI, operations, API, security and agent deployment.

## 0.2.3

- Introduced Fleet-style outbound managed-agent enrollment.
- Added short-lived enrollment tokens and per-agent credentials.
- Added one-command Windows/Linux bootstrap installers.
- Added native Windows Service/systemd agent installation.
- Added outbound telemetry aggregation through the Control API.
