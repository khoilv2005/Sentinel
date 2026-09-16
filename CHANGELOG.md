# Changelog

## Unreleased — v0.4 unified operations

### Product consolidation

- Reduced the primary operator navigation to Dashboard, Assets, Problems, Operational Events, Monitoring, Alerts, Availability & SLA, Access, Audit and Settings.
- Consolidated Hosts and Inventory into the Assets workflow.
- Moved Services, Topology and Discovery under Assets.
- Consolidated Agentless, Managed Agents, Credentials and Agent Policies under Monitoring.
- Consolidated Monitoring Rules, Notifications and Maintenance under Alerts.
- Removed separate SNMP and Integrations concepts from primary navigation; SNMP is a Monitoring method and the integration list is a capability catalog under Settings.
- Added compatibility redirects for older UI routes.

### Discovery and health boundaries

- Discovery now enriches inventory identity only and no longer changes runtime `Device.state` merely because a scan sees or misses a target.
- Explicit Add/Monitor operations create unknown assets until monitoring produces runtime evidence.
- Added regression coverage proving discovery can enrich an existing asset without changing its pre-existing health state.

### Unified monitoring

- Added canonical `/api/v1/monitoring/*` assignment APIs while retaining hidden `/api/v1/agentless/*` compatibility aliases.
- Renamed the Docker `agentless-worker` service to `collector-worker`; the Python module/database compatibility names remain temporarily.
- Added per-assignment `collector_telemetry_latest` storage keyed by monitor ID so WinRM, SSH and SNMP samples on one asset no longer overwrite one another.
- Added source-aware compatibility aggregation that prefers richer WinRM/SSH telemetry over generic SNMP unless the preferred sample becomes stale.
- Added health aggregation so one failed remote method cannot mark an asset down while another enabled method remains healthy; all enabled remote methods must reach the failure threshold when no managed agent is online.
- Added regression tests for API aliases, multi-method telemetry isolation and multi-method health aggregation.

### Alerting architecture

- Made the SentinelView Control API the single alert-evaluation source: telemetry -> Monitoring Rules -> Services -> Problems -> Notifications.
- Removed independent Sentinel threshold rules from Prometheus to prevent alert-threshold drift and duplicate alert engines.
- Retained Prometheus as the time-series/history backend and Grafana as optional advanced analytics.

### API and route hygiene

- Added a transitional modular Control API entrypoint that preserves the existing implementation while removing duplicate method/path registrations.
- Ensured notification and maintenance/availability requests resolve to their modular implementations rather than stale inline duplicates.
- Added route-uniqueness regression coverage.

### Documentation and operations

- Rewrote the README around the unified operator workflow.
- Added `docs/MONITORING_ARCHITECTURE.md` as the architecture source of truth.
- Updated UI, API, remote-monitoring and operations guides.
- Updated integration CI job naming to use remote-collector terminology.
- Added an upgrade note for the `collector-worker` service rename without deleting persistent volumes.

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
