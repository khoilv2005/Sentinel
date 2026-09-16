# SentinelView v0.4 — architecture consolidation

SentinelView is a self-hosted infrastructure monitoring platform with a first-party operations UI, PostgreSQL inventory, managed agents, remote WinRM/SSH/SNMP collection, Prometheus history, notification delivery, maintenance/SLA handling and optional Grafana analytics.

v0.4 simplifies the product around one operator model:

```text
Asset
  ↓
Monitoring methods
  ├── Managed Agent
  ├── WinRM
  ├── SSH
  ├── SNMP
  └── reachability / exporter integrations
  ↓
Services
  ↓
Problems
  ↓
Notifications
  ↓
Availability / SLA
```

The goal is to stop exposing implementation components such as **Discovery**, **Inventory**, **Agentless**, **SNMP** and **Agent** as unrelated top-level products when they are parts of one Asset lifecycle.

> v0.4 is currently being consolidated on the `refactor/v0.4-consolidation` branch. Compatibility routes/fields from v0.3 remain temporarily so existing labs can migrate without deleting data.

---

## Product model

SentinelView now uses six conceptual domains.

### 1. Assets

Answers: **What infrastructure exists?**

An Asset is the single inventory record currently stored by the `Device` model.

Assets can enter SentinelView through:

- network discovery;
- manual add;
- managed-agent enrollment;
- future import/integration paths.

Discovery only finds/enriches Assets. It does **not** own operational health.

### 2. Collection

Answers: **How is data collected from the Asset?**

Supported paths include:

- Managed Sentinel Agent;
- WinRM/CIM for Windows;
- SSH for Linux/Unix;
- SNMP for network/infrastructure devices;
- Prometheus exporter integrations for selected advanced collection.

Remote collection is represented as a **Monitoring Assignment**. A Monitoring Assignment can only target an Asset that already exists.

### 3. Monitoring

Answers: **What does current telemetry mean?**

SentinelView derives Services from telemetry and monitoring-method state.

Overall Asset health is:

```text
UP
DEGRADED
DOWN
UNKNOWN
```

Examples:

```text
SSH = UP
SNMP = DOWN
→ Asset = DEGRADED
```

```text
Managed Agent = UP
→ Asset = UP
```

```text
No configured monitoring result
→ Asset = UNKNOWN
```

### 4. Alerting

Answers: **What requires attention and who should be notified?**

The canonical pipeline is:

```text
Telemetry
  ↓
Monitoring Rules
  ↓
Services
  ↓
Problems
  ↓
Notifications
```

SentinelView Monitoring Rules are the single product alert source of truth. The checked-in Prometheus rule file is intentionally empty so Prometheus does not maintain a conflicting second threshold set.

### 5. Reporting

Answers: **What availability/SLA was achieved?**

Availability uses recorded state-change history. Maintenance windows may be excluded from the eligible SLA denominator.

### 6. Platform

Answers: **Who may operate/configure SentinelView?**

Includes local users/roles, audit history and platform settings.

---

# Primary UI

Open:

```text
http://localhost:3001
```

The consolidated navigation is intentionally small.

```text
MONITOR
├── Dashboard
├── Assets
├── Problems
└── Operational Events

MANAGE / CONFIGURE
├── Monitoring
└── Alerts

REPORT
└── Availability & SLA

PLATFORM
├── Access
├── Audit
└── Settings
```

## Assets workspace

`Assets` replaces the old conceptual split between Hosts and Inventory.

Tabs:

```text
All assets
Services
Topology
Discover
```

Asset Detail contains identity/inventory information together with monitoring state, telemetry, Services and Problems.

## Monitoring workspace

Tabs:

```text
Managed agent
Remote collectors
Credentials
Agent settings
```

`Remote collectors` replaces the old top-level **Agentless** concept.

Supported remote methods:

```text
WinRM
SSH
SNMP
```

The historical SNMP exporter screen is demoted to:

```text
Settings -> Legacy SNMP exporter
```

New SNMP monitoring should be configured as a Monitoring Assignment.

## Alerts workspace

Tabs:

```text
Rules
Notifications
Maintenance
```

---

# Quick start

## Windows PowerShell

```powershell
cd D:\Project\Sentinel
Copy-Item .env.example .env
notepad .env
```

Replace development values before non-lab use, especially:

```text
POSTGRES_PASSWORD
SENTINEL_DB_URL
SENTINEL_API_KEY
SENTINEL_ADMIN_PASSWORD
SENTINEL_SESSION_SECRET
SENTINEL_CREDENTIAL_SECRET
GF_SECURITY_ADMIN_PASSWORD
```

The password inside `SENTINEL_DB_URL` must match `POSTGRES_PASSWORD`.

Start:

```powershell
docker compose up -d --build
docker compose ps
```

## Linux

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose ps
```

## Core services

| Service | Purpose |
|---|---|
| `postgres` | inventory/configuration/state |
| `control-api` | SentinelView control plane/API |
| `discovery-worker` | inventory discovery only |
| `collector-worker` | WinRM/SSH/SNMP remote collection |
| `notification-worker` | asynchronous notification delivery |
| `web-ui` | first-party UI |
| `prometheus` | time-series/history backend |
| `snmp-exporter` | optional Prometheus SNMP enrichment |
| `blackbox-exporter` | reachability/synthetic probe foundation |
| `grafana` | advanced analytics |

Loki remains optional through its Compose profile.

## URLs

| Component | URL |
|---|---|
| SentinelView | `http://localhost:3001` |
| API docs | `http://localhost:8080/docs` |
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |
| SNMP Exporter | `http://localhost:9116` |
| Blackbox Exporter | `http://localhost:9115` |

---

# Recommended first workflow

## 1. Discover or add Assets

Open:

```text
Assets -> Discover
```

Example:

```text
CIDR: 192.168.1.0/24
Site: home-lab
```

Only authorized private ranges are accepted.

Discovery may record:

- IP address;
- hostname;
- MAC when available;
- open ports;
- inferred device class;
- site;
- observation history.

Discovery does **not** mark an Asset DOWN because a later scan misses it.

## 2. Assign a monitoring method

Open:

```text
Monitoring -> Remote collectors
```

Choose an Asset and method:

```text
Windows       -> WinRM
Linux/Unix    -> SSH
Switch/router -> SNMP
UPS/appliance -> SNMP
```

A remote Monitoring Assignment cannot create an arbitrary inventory record. Add/discover the Asset first.

Compatibility scope values currently behave as:

```text
selected   = selected existing Assets
discovered = observed Assets inside the CIDR
cidr_all   = all inventoried Assets inside the CIDR
```

For a `/24`, SentinelView can still list all 254 usable candidate addresses, but monitoring does not create 254 fake placeholder Assets.

## 3. Optional Managed Agent

Open:

```text
Monitoring -> Managed agent
```

Generate a short-lived installer command. A remote endpoint must use the SentinelView host LAN/DNS Control API URL, for example:

```text
http://192.168.1.10:8080
```

Do not use `localhost` for a different endpoint machine.

The managed agent:

1. downloads the agent binary;
2. verifies SHA-256;
3. enrolls using a short-lived token;
4. receives a unique per-agent credential;
5. installs as Windows Service/systemd service;
6. pushes telemetry outbound.

Managed Agent is an enhanced monitoring method, not a prerequisite for basic performance metrics.

## 4. Review health

Use:

```text
Dashboard
Assets
Assets -> Services
Problems
Operational Events
```

One failing collection method does not necessarily mean the entire Asset is DOWN. Mixed healthy/failed methods produce DEGRADED health.

---

# Remote telemetry architecture

v0.3 stored one remote-telemetry row per Device. This meant different collectors could overwrite one another.

v0.4 stores latest telemetry per Monitoring Assignment:

```text
Asset
  ├── SSH assignment  -> monitoring_telemetry_latest row
  └── SNMP assignment -> monitoring_telemetry_latest row
```

A compatibility aggregate is currently maintained in:

```text
agentless_telemetry_latest
```

for existing Prometheus/UI readers.

Aggregation policy currently prefers:

- WinRM/SSH for host CPU/RAM/disk-style values;
- SNMP for interface lists when available.

Therefore a partial SNMP poll cannot erase RAM/disk data produced by SSH.

---

# SNMP

The canonical product concept is:

```text
Monitoring method = SNMP
```

Direct SNMP polling uses encrypted credential profiles.

A SNMP credential can optionally opt the same assignment into Prometheus `snmp_exporter` enrichment with credential options such as:

```json
{
  "exporter_auth": "public_v2",
  "exporter_module": "if_mib"
}
```

HTTP service discovery exposes only the exporter profile name/module and Asset metadata. It never exposes SNMP communities/passwords.

Legacy `Device.snmp_*` targets remain temporarily for compatibility and are not the preferred new configuration path.

Vendor-specific deep profiles such as APC UPS and Vertiv remain roadmap work until actual MIB/profile support is implemented.

---

# Problems, notifications and maintenance

## Monitoring Rules

Monitoring Rules determine Service state for product metrics such as CPU, memory, disk and Managed Agent availability.

## Problems

Warning/critical Services create persistent Problems. Operators can acknowledge active Problems; recovery resolves them.

## Notifications

Supported channels:

```text
webhook
Slack
Microsoft Teams
Telegram
SMTP email
```

Problem lifecycle transitions are queued in PostgreSQL and delivered asynchronously by `notification-worker` with bounded retry/backoff.

Sensitive channel configuration is encrypted at rest using `SENTINEL_CREDENTIAL_SECRET` and redacted from API responses.

## Maintenance

Maintenance can target:

- one Asset;
- a site;
- all Assets.

Options:

- suppress matching problem notifications;
- exclude the overlapping interval from SLA accounting.

---

# Prometheus and Grafana

Prometheus is the time-series/history backend.

It scrapes SentinelView central metrics and optional exporter targets. It is **not** a second SentinelView alert source of truth.

Grafana remains available for advanced analysis and PromQL dashboards but is not required for normal operator workflows.

---

# Authentication and roles

Local roles:

```text
admin
operator
viewer
```

UI authentication uses signed bearer sessions. Current local-user enabled/role state is re-read for authenticated requests, so disabling a user invalidates existing access and role changes apply without waiting for token expiration.

Automation may use:

```text
X-API-Key: <SENTINEL_API_KEY>
```

Managed agents use their own dedicated bearer credentials.

---

# Persistence

Docker volumes include:

```text
postgres-data
prometheus-data
grafana-data
loki-data
```

Preserve state:

```bash
docker compose down
```

Destroy the lab and volumes only when intentional:

```bash
docker compose down -v
```

Do not use `-v` just to apply an upgrade.

---

# v0.3 -> v0.4 compatibility

During migration, several old names remain internally:

```text
AgentlessMonitor
agentless_worker.py
/api/v1/agentless/*
agentless_telemetry_latest
Device.agent_*
Device.snmp_*
```

New product/API terminology is:

```text
Monitoring Assignment
collector-worker
/api/v1/monitoring/*
monitoring_telemetry_latest
```

The old `/api/v1/agentless/*` routes are deprecated but temporarily functional.

`SENTINEL_AGENTLESS_WORKERS` is also accepted as a fallback for the new:

```text
SENTINEL_COLLECTOR_WORKERS
```

The production ASGI entrypoint removes exact duplicate legacy route registrations so runtime/OpenAPI expose one implementation per path+method while the monolithic source is being migrated.

---

# Development and QA

Core CI validates:

- Python API/unit/regression tests;
- Go module verification/tests;
- Linux and Windows agent builds;
- JavaScript syntax;
- configuration validation.

Disposable integration CI validates:

- clean no-cache application Docker build;
- real OpenSSH collection;
- real SNMP daemon collection;
- remote collector failure/recovery behavior;
- real WinRM/CIM collection on a Windows runner.

v0.4 regression coverage additionally checks:

- discovery cannot override operational health;
- monitoring cannot implicitly create Assets;
- multiple remote methods cannot overwrite each other's raw/latest telemetry;
- mixed collector health produces DEGRADED;
- SNMP exporter targets can derive from SNMP Monitoring Assignments;
- the runtime ASGI app exposes no duplicate path+method routes.

---

# Documentation

- `docs/ARCHITECTURE_V04.md` — v0.4 consolidation design and migration phases.
- `docs/UI_GUIDE.md` — consolidated UI workflows.
- `docs/API.md` — API groups and compatibility routes.
- `docs/AGENT_DEPLOYMENT.md` — Managed Agent deployment.
- `docs/AGENTLESS_MONITORING.md` — remote monitoring details; historical filename retained for compatibility.
- `docs/OPERATIONS.md` — operations/troubleshooting.
- `PROJECT_STATUS.md` — current implemented/migration status.

---

# Current limitations

SentinelView does not currently claim:

- commercial-scale vendor plugin coverage;
- complete APC/Vertiv/Cisco/Fortinet/etc. deep MIB packs;
- automatic LLDP/CDP topology discovery;
- enterprise on-call calendars/policy trees;
- recurring maintenance rules;
- OIDC/LDAP/SAML;
- object-level/site-level granular RBAC;
- distributed remote collectors;
- HA;
- historical SLA data before state-transition recording began;
- MSI/DEB/RPM release packages;
- signed staged automatic agent updates.

These remain roadmap items rather than duplicated placeholder features in the main UI.
