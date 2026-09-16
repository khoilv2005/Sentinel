# SentinelView

SentinelView is a self-hosted infrastructure monitoring platform with a first-party operations UI, PostgreSQL inventory, optional managed endpoint agents, remote WinRM/SSH/SNMP collection, Prometheus history, notification delivery, maintenance and SLA reporting.

The v0.4 consolidation simplifies the product around one operator flow:

```text
Assets -> Monitoring -> Services / Problems -> Notifications -> SLA
```

Backend components such as `snmp_exporter`, Blackbox Exporter, Prometheus and the managed agent still exist, but they are no longer presented as unrelated product features.

> SentinelView is currently a lab/development and portfolio-grade monitoring platform. It does not claim feature-for-feature parity with commercial Checkmk, Zabbix, Datadog or Elastic deployments.

## Core concepts

SentinelView has six clear domains:

| Domain | Question |
|---|---|
| Assets | What infrastructure objects exist? |
| Collection | How is data collected from each asset? |
| Monitoring | What is the current health/service state? |
| Alerting | What problems exist and who should be notified? |
| Reporting | What availability/SLA has been achieved? |
| Platform | Who can access or change the system? |

### Discovery is not Monitoring

**Discovery** scans an authorized private network to find assets and enrich identity metadata such as hostname, MAC address, open ports, class and site.

Discovery does **not** decide operational health. A scan miss no longer marks an asset down.

**Monitoring** collects runtime evidence from an asset through one or more methods:

| Method | Typical target | Purpose |
|---|---|---|
| Managed Sentinel Agent | Windows/Linux endpoint | Rich outbound endpoint telemetry |
| WinRM | Windows | CPU/RAM/disk/process/network without Sentinel Agent |
| SSH | Linux/Unix | CPU/RAM/disk/process/network without Sentinel Agent |
| SNMP | Switch/router/UPS/printer/appliance | Device and infrastructure telemetry |
| ICMP/Blackbox | Reachable network targets | Synthetic reachability/latency backend |

A single asset may use multiple monitoring methods.

## Primary UI

Open:

```text
http://localhost:3001
```

The primary navigation is intentionally compact:

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

Contextual sub-views expose detail without creating more top-level products:

```text
Assets
├── All assets
├── Services
├── Topology
└── Discovery

Monitoring
├── Remote methods
├── Managed Agent
├── Credentials
└── Agent settings

Alerts
├── Rules
├── Notifications
└── Maintenance
```

The older `Inventory`, `Agentless`, separate `SNMP`, and `Integrations` navigation concepts are consolidated into these workflows. Legacy routes/API aliases remain temporarily for compatibility.

## Architecture

```text
                       SentinelView UI :3001
                               |
                               v
                        Control API :8080
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
            Assets         Monitoring        Alerting
              |                |                |
          PostgreSQL      Collector layer    Rule engine
                               |                |
                    +----------+----------+     v
                    |          |          |  Problems
                 Managed     Remote     Blackbox  |
                  Agent     collectors    /ICMP   v
                            /   |   \          Notifications
                         WinRM SSH SNMP
                               |
                               v
                           Telemetry
                               |
                       +-------+-------+
                       |               |
                  Current state     Prometheus
                                       |
                                     History
                                       |
                                     Grafana
```

### Single alert source of truth

SentinelView Control API owns alert evaluation:

```text
Telemetry
  -> Monitoring Rules
  -> Services
  -> Problems
  -> Notifications
```

Prometheus stores time-series/history and supports Grafana/host-history queries. SentinelView does not maintain a second independent set of Prometheus alert thresholds.

## Remote monitoring data model

The operator-facing concept is a **monitoring assignment**. Current remote methods are WinRM, SSH and SNMP.

New API paths:

```text
GET  /api/v1/monitoring/candidates
GET  /api/v1/monitoring/assignments
POST /api/v1/monitoring/assignments/bulk
POST /api/v1/monitoring/test
POST /api/v1/monitoring/assignments/{id}/poll
DELETE /api/v1/monitoring/assignments/{id}
```

Legacy `/api/v1/agentless/*` routes remain compatibility aliases during the v0.4 transition.

Each remote assignment stores its latest sample independently in `collector_telemetry_latest`, keyed by monitor ID. This prevents a generic SNMP poll from overwriting richer SSH/WinRM telemetry from the same asset.

The older device-level remote telemetry table is maintained temporarily as a compatibility aggregate for existing Host Detail and Prometheus export.

## Health behavior

Runtime health is aggregated across monitoring evidence:

- an online Managed Agent is positive evidence that an asset is up;
- any healthy remote monitoring assignment is positive evidence that an asset is up;
- failure of one remote method does not make the whole asset down while another enabled method remains healthy;
- an asset transitions down only when every enabled remote assignment reaches the configured failure threshold and no Managed Agent is online;
- an asset with no runtime evidence remains unknown;
- the UI may present an otherwise reachable asset as **degraded** when it has active unhealthy services/problems.

## Quick start

### Windows PowerShell

```powershell
cd D:\Project\Sentinel
Copy-Item .env.example .env
notepad .env
```

At minimum replace development values for:

```text
SENTINEL_API_KEY
SENTINEL_ADMIN_PASSWORD
SENTINEL_SESSION_SECRET
SENTINEL_CREDENTIAL_SECRET
POSTGRES_PASSWORD
SENTINEL_DB_URL
GF_SECURITY_ADMIN_PASSWORD
```

Keep the password embedded in `SENTINEL_DB_URL` aligned with `POSTGRES_PASSWORD`.

Start:

```powershell
docker compose up -d --build
docker compose ps
```

### Linux

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
```

Do not use `docker compose down -v` for routine upgrades; that removes persistent volumes.

## Core services

A normal deployment includes:

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

Loki is optional and enabled through its Compose profile.

### URLs

| Component | URL | Purpose |
|---|---|---|
| SentinelView | `http://localhost:3001` | Primary operations UI |
| Control API | `http://localhost:8080/docs` | API docs / automation |
| Grafana | `http://localhost:3000` | Advanced analytics |
| Prometheus | `http://localhost:9090` | Metrics/history/PromQL |
| SNMP Exporter | `http://localhost:9116` | Internal SNMP exporter |
| Blackbox Exporter | `http://localhost:9115` | Synthetic probing backend |

## First workflow

### 1. Discover assets

Open:

```text
Monitor -> Assets -> Discovery
```

Example:

```text
CIDR: 192.168.1.0/24
Site: home-lab
```

A `/24` contains 254 usable host addresses. Only scan networks you own or are authorized to manage.

Discovery creates/enriches asset inventory. It does not mark missing assets down.

### 2. Configure Monitoring

Open:

```text
Configure -> Monitoring
```

Use **Remote methods** for WinRM/SSH/SNMP or **Managed Agent** for Sentinel Agent enrollment.

For remote methods, create/select an encrypted credential and choose a target scope:

```text
Selected IPs
Discovered assets in CIDR
Entire private CIDR
```

An explicitly added target starts `unknown` until monitoring returns runtime evidence.

### 3. Review Assets and Problems

Use:

```text
Monitor -> Assets
Monitor -> Problems
```

Asset detail can show latest telemetry, services, active problems and Prometheus-backed CPU/memory history.

### 4. Configure Alerts

Open:

```text
Configure -> Alerts
```

Use:

- **Rules** for monitoring thresholds;
- **Notifications** for webhook, Slack, Teams, Telegram or SMTP delivery;
- **Maintenance** for planned suppression and optional SLA exclusion.

### 5. Review SLA

Open:

```text
Report -> Availability & SLA
```

Availability is calculated from recorded state transitions. Maintenance windows marked for SLA exclusion are removed from the eligible denominator.

## Managed Agent

The Sentinel Agent is optional. It uses outbound enrollment/check-in/telemetry and does not require Prometheus to connect directly to endpoint port `9123`.

Generate the installer under:

```text
Configure -> Monitoring -> Managed Agent
```

For a remote endpoint, supply a Control API URL reachable from that endpoint, for example:

```text
http://192.168.1.10:8080
```

Do not use `localhost` unless SentinelView and the endpoint are the same machine.

## Credentials

WinRM/SSH/SNMP secrets are encrypted with:

```text
SENTINEL_CREDENTIAL_SECRET
```

Use a strong, stable value. Changing it without deliberate credential rotation makes existing encrypted credentials unreadable.

API responses never return plaintext credential secrets.

## Notifications

Supported notification channel types:

```text
webhook
slack
teams
telegram
email (SMTP)
```

Problem open/escalation/recovery/post-maintenance transitions enter a persistent delivery queue. The `notification-worker` performs delivery with bounded retry/backoff. Active maintenance can suppress matching notifications.

## Grafana

Grafana is optional advanced analytics, not the primary SentinelView UI.

Grafana stores its admin credential in the persistent `grafana-data` volume. Editing `GF_SECURITY_ADMIN_PASSWORD` after initialization does not rotate the stored password. Use the explicit reset helper on Windows:

```powershell
.\scripts\reset-grafana-admin.ps1 -Password 'new-password'
```

## Upgrade from the older agentless-worker naming

The v0.4 consolidation renames the Docker service to `collector-worker` while retaining the Python module/database compatibility names temporarily.

Upgrade without deleting volumes:

```powershell
git pull --ff-only origin main
docker compose down
docker compose up -d --build
docker compose ps
```

`docker compose down` removes the obsolete service container. Do **not** add `-v`.

## Automated validation

GitHub Actions validates:

- Python API/unit/regression tests;
- unified monitoring boundary tests;
- JavaScript syntax/configuration;
- Go module/tests and Linux/Windows agent builds;
- clean no-cache Docker application build;
- real disposable SSH collection;
- real disposable SNMP collection;
- failure/recovery behavior;
- real WinRM/CIM collection on Windows runner.

## Current limitations

SentinelView does not currently claim:

- commercial-scale vendor monitoring packs;
- automatic LLDP/CDP topology discovery;
- enterprise on-call calendars/policy trees/multi-stage escalation;
- recurring maintenance rules beyond explicit start/end windows;
- OIDC/LDAP/SAML;
- fine-grained object-level RBAC;
- distributed collectors/HA;
- historical SLA data before state-transition recording began;
- MSI/DEB/RPM release packages;
- signed staged automatic agent updates.

## Documentation

- `docs/UI_GUIDE.md` — operator UI workflows.
- `docs/API.md` — API groups and compatibility aliases.
- `docs/MONITORING_ARCHITECTURE.md` — product/domain architecture.
- `docs/AGENTLESS_MONITORING.md` — remote monitoring transition details.
- `docs/OPERATIONS.md` — deployment and troubleshooting.
- `PROJECT_STATUS.md` — implemented scope and current limitations.

## License

See `LICENSE`.
