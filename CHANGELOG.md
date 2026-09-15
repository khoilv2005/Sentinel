# Changelog

## Unreleased — audit hardening

### Agentless validation

- Added disposable real-target integration coverage for WinRM/CIM on Windows, OpenSSH on Linux and a local SNMP daemon.
- Added scheduler regression coverage for three consecutive collection failures followed by successful recovery.
- Added a safe SQLite-backed entire-`/24` assignment regression that proves 254 unique monitor assignments and idempotent re-application.
- Added a hosted no-cache Docker application build so local Docker DNS availability is not the only build-validation path.
- Continued Go 1.25 managed-agent verification and Linux/Windows cross-builds in CI, so host-installed Go is not required for runtime deployment.

### Notifications and maintenance

- Added a persistent notification delivery queue and `notification-worker`.
- Added webhook, Slack, Microsoft Teams, Telegram and SMTP delivery with bounded retry/backoff.
- Added test delivery and recent-delivery status APIs/UI.
- Added encryption at rest and API redaction for notification channel delivery configuration.
- Added automatic problem opened/escalated/recovered/post-maintenance notification transitions.
- Added active maintenance suppression for matching problem notifications.
- Added maintenance-aware SLA accounting that removes excluded intervals from the eligible denominator.

### Audit fixes and operations

- Fixed bootstrap instability when multiple monitoring rules legitimately use the same metric by identifying seeded defaults by rule name.
- Fixed stale bearer-session authorization so disabled users are rejected immediately and role changes apply to already-issued sessions.
- Added consistent `.env.example` PostgreSQL credentials for clean first boot.
- Added explicit Grafana persistent-admin password rotation helper instead of silently resetting existing state.
- Added agentless-worker problem synchronization after poll success/failure transitions.
- Updated README, UI guide, operations guide, project status and roadmap to reflect implemented behavior.

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
