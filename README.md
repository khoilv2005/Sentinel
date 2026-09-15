# SentinelView v0.3.0

SentinelView is a self-hosted infrastructure monitoring and observability platform designed around a **first-party operations UI**, outbound managed agents, Prometheus-compatible metrics, PostgreSQL inventory, SNMP/blackbox integrations and Grafana for optional advanced analytics.

v0.3.0 changes the product model significantly: **SentinelView UI is now the primary interface**. Operators no longer need Grafana, Prometheus or Swagger for normal monitoring workflows.

> Scope statement: v0.3.0 is a substantial lab/development platform and CV-grade monitoring project. It is not a claim of feature-for-feature parity with the commercial editions of Checkmk, Zabbix, Datadog or Elastic. The repository clearly separates implemented features from roadmap items.

## What v0.3.0 adds

The first-party UI at `http://localhost:3001` now includes:

- Overview dashboard with host/service/problem/agent health.
- Hosts table with state, site, OS, agent status, services and problem counts.
- Host detail with latest CPU/RAM/disk/process telemetry and Prometheus history charts.
- Service-centric monitoring view.
- Active Problems view with acknowledgement.
- Operational Events view.
- Network Discovery UI with live scan progress.
- Infrastructure Inventory.
- Managed Agent onboarding and one-command Windows/Linux installation.
- Agent Policies with central interval/collector changes.
- Monitoring Rules UI for CPU, memory, disk and agent availability thresholds.
- Topology visualization.
- SNMP target management.
- Integration catalog.
- Notification channel configuration foundation.
- Maintenance windows.
- Availability and SLA definitions.
- Local users and roles (`admin`, `operator`, `viewer`).
- Audit log.
- Global host/event search.
- Platform settings and links to advanced Grafana/Prometheus views.

Grafana remains available, but is intentionally demoted to **advanced analytics** rather than the main day-to-day interface.

---

## Architecture

```text
                         Browser
                           |
                           v
                 SentinelView UI :3001
                           |
                    session auth
                           |
                           v
                  Control API :8080
                    /    |     \
                   /     |      \
                  v      v       v
            PostgreSQL  Prometheus  Agent artifacts
             inventory    :9090      Windows/Linux
             config         |
             events         v
             problems     Grafana :3000
             users        advanced analysis
                 ^
                 |
       +---------+----------+
       |                    |
       | HTTPS/HTTP         | discovery/SNMP
       | outbound           |
       v                    v
 Sentinel Agent        Network devices
 Windows/Linux         Router/Switch/UPS/etc.
```

### Control plane

FastAPI owns:

- inventory;
- discovery jobs;
- managed-agent enrollment and credentials;
- latest endpoint telemetry;
- service-state derivation;
- problem lifecycle;
- monitoring rules;
- maintenance metadata;
- availability/SLA definitions;
- local UI sessions and roles;
- audit events;
- topology metadata;
- installation artifacts.

### Metrics plane

Prometheus scrapes one central SentinelView `/metrics` endpoint for managed-agent metrics. Managed agents send telemetry outbound to the Control API, so endpoint machines do **not** require inbound Prometheus access.

### Visualization

SentinelView UI renders normal operations views itself. Grafana is still provisioned for advanced PromQL dashboards and long-form troubleshooting.

---

## Requirements

Recommended development/lab host:

- Windows 10/11 + Docker Desktop, or Linux with Docker Engine.
- Docker Compose v2.
- 8 GB RAM minimum; 16 GB+ recommended for comfortable use.
- Internet access on the first build so Docker can download images and Go modules.

You do **not** need Python, Go or Node installed on the host to run the containerized platform.

---

## Quick start

### Windows PowerShell

```powershell
cd D:\Project\sentinelview
Copy-Item .env.example .env
notepad .env
```

At minimum, change:

```text
SENTINEL_API_KEY=
SENTINEL_ADMIN_PASSWORD=
SENTINEL_SESSION_SECRET=
POSTGRES_PASSWORD=
GF_SECURITY_ADMIN_PASSWORD=
```

Then:

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

### URLs

| Component | URL | Purpose |
|---|---|---|
| SentinelView | `http://localhost:3001` | Primary operations UI |
| Control API | `http://localhost:8080/docs` | API documentation / automation |
| Grafana | `http://localhost:3000` | Advanced analytics |
| Prometheus | `http://localhost:9090` | Metrics engine / PromQL |
| SNMP Exporter | `http://localhost:9116` | SNMP translation |
| Blackbox Exporter | `http://localhost:9115` | ICMP/TCP/HTTP-style probing foundation |

### First login

The UI bootstrap user is controlled by:

```text
SENTINEL_ADMIN_USER
SENTINEL_ADMIN_PASSWORD
```

The default development fallback is `admin/admin` when those variables are absent. The provided `.env.example` intentionally asks you to replace the password.

The bootstrap user is created on the **first database start**. Changing the environment variable later does not silently overwrite an existing user's password; change it from the Users page or recreate the lab database.

---

## First test workflow

### 1. Open SentinelView

Go to:

```text
http://localhost:3001
```

Sign in.

### 2. Discover your LAN

Open:

```text
Manage -> Discovery
```

Example:

```text
CIDR: 192.168.1.0/24
Site: home-lab
```

Click **Start discovery**.

Only private network ranges are accepted by the backend.

### 3. Inspect hosts

Open:

```text
Monitor -> Hosts
```

Click a discovered device to open Host Detail.

Discovery-only devices provide reachability/inventory data. CPU, RAM, disks and process metrics require a managed endpoint agent or another integration.

### 4. Install a Windows/Linux agent

Open:

```text
Manage -> Agents
```

Choose OS, policy, site and the SentinelView Control API URL, for example:

```text
http://192.168.1.10:8080
```

Do **not** use `localhost` for a remote endpoint.

Click **Generate install command**, then run the command on the endpoint as Administrator/root.

The bootstrap installer:

1. downloads the agent from SentinelView;
2. verifies SHA-256;
3. uses the short-lived enrollment token;
4. creates a persistent per-agent credential;
5. installs a Windows Service or systemd service;
6. starts the agent;
7. pushes telemetry outbound to SentinelView.

No manual inbound port 9123 rule is required for managed-agent mode.

### 5. Observe metrics

After a few telemetry intervals:

```text
Hosts -> <host>
```

will display:

- CPU utilization;
- memory utilization;
- disks;
- process count;
- uptime;
- network collector status;
- services;
- active problems;
- historical CPU/memory charts from Prometheus.

---

## Main UI areas

### Monitor

`Overview` summarizes hosts, services, problems, agents, sites and recent events.

`Hosts` is the primary asset health view.

`Services` turns raw telemetry into service states such as:

```text
Host availability
Sentinel Agent
CPU utilization
Memory utilization
Disk C:\
Process count
Interface Ethernet
```

`Problems` stores current warning/critical conditions. Operators can acknowledge active problems.

`Events` records discovery, enrollment and state-change events.

`Topology` renders known topology edges and all monitored nodes.

### Manage

`Discovery` starts private CIDR scans and displays progress/history.

`Inventory` shows IP, MAC, vendor/model, class, site, agent and SNMP state.

`Agents` implements Fleet-style enrollment.

`Agent Policies` centrally control telemetry/check-in intervals and collectors.

### Configure

`Monitoring Rules` control service thresholds used by the first-party UI problem engine.

Default rules are seeded for:

```text
CPU utilization       warning 80% / critical 95%
Memory utilization    warning 85% / critical 95%
Disk utilization      warning 85% / critical 95%
Managed agent         critical when unavailable
```

`SNMP` manages Prometheus/snmp_exporter targets.

`Integrations` shows implemented and planned integration packs.

`Notifications` stores notification-channel configurations. Automatic notification dispatch/routing is explicitly a later phase; v0.3.0 does not pretend that saved channels are already sending production alerts.

`Maintenance` stores maintenance-window and SLA-exclusion metadata.

### Report

`Availability & SLA` calculates availability using state-change events. Historical accuracy begins from v0.3.0 state-transition recording onward; old databases do not magically gain pre-upgrade history.

### Platform

`Users & Roles` manages local users:

- `admin`: platform administration;
- `operator`: monitoring operations and write actions;
- `viewer`: read-oriented UI access.

`Audit Log` records important administrative actions.

`Settings` shows platform configuration and advanced component links.

---

## Managed agent architecture

The default v0.3.0 architecture is outbound:

```text
Endpoint
   |
   | enroll once using short-lived sv_enr_* token
   v
Control API
   |
   | returns unique sv_agt_* credential
   v
Endpoint service
   |
   | check-in + telemetry outbound
   v
Control API -> /metrics -> Prometheus -> SentinelView/Grafana
```

Enrollment tokens and persistent agent credentials are different secrets.

The database stores hashes rather than plaintext enrollment/agent credentials.

See `docs/AGENT_DEPLOYMENT.md`.

---

## SNMP

SNMP targets are stored in SentinelView inventory and exported through HTTP service discovery:

```text
Device -> snmp_exporter -> Prometheus
```

v0.3.0 includes generic target management and the `if_mib` path. Vendor-specific packs (APC, Vertiv, Cisco/Fortinet/MikroTik depth, etc.) remain explicit roadmap work rather than simulated support.

---

## Problems vs Prometheus alerts

SentinelView currently has two complementary layers:

1. **First-party problem engine**: derives current services/problems from latest control-plane telemetry and SentinelView monitoring rules.
2. **Prometheus rule files**: provide Prometheus-native alert expressions for advanced monitoring workflows.

Future releases can unify notification routing and Alertmanager-style dispatch while preserving the first-party UI state model.

---

## Authentication

v0.3.0 introduces local UI session authentication.

The browser sends a signed bearer session token to the Control API through the UI reverse proxy.

External automation remains compatible with:

```text
X-API-Key: <SENTINEL_API_KEY>
```

This is useful for scripts and API clients.

For production-scale enterprise deployment, OIDC/LDAP/SAML and more granular permission mapping remain roadmap items.

---

## Persistence

Docker volumes:

```text
postgres-data
prometheus-data
grafana-data
loki-data
```

Stop without deleting state:

```bash
docker compose down
```

Delete the full lab including stored data:

```bash
docker compose down -v
```

Do not use `-v` unless you intend to remove the database and metrics history.

---

## Upgrade from v0.2.3

v0.3.0 adds new tables rather than altering the v0.2.3 managed-agent tables, so `Base.metadata.create_all()` can create the new UI-domain tables in an existing lab database.

Added tables include:

```text
problems
audit_events
maintenance_windows
notification_channels
sla_definitions
local_users
```

Existing devices, scans, managed agents, policies and telemetry remain intact.

Because this project has not yet introduced Alembic migrations, take a database backup before non-trivial upgrades. Formal schema migrations are a roadmap item.

---

## Development and tests

### API tests

```bash
PYTHONPATH=services/control-api \
SENTINEL_DB_URL=sqlite:////tmp/sentinel-test.db \
pytest -q services/control-api/tests
```

### UI syntax

```bash
node --check services/web-ui/js/api.js
node --check services/web-ui/js/ui.js
node --check services/web-ui/js/app.js
```

### Configuration validation

```bash
pip install pyyaml
python scripts/validate-config.py
```

### Go agent

Requires Go 1.25+:

```bash
cd agents/sentinel-agent
go mod tidy
go mod download all
go mod verify
go test ./...
```

The server Docker image also cross-compiles Linux and Windows agent artifacts during build.

---

## Useful Docker commands

```bash
# Start / rebuild
docker compose up -d --build

# Status
docker compose ps

# Follow all logs
docker compose logs -f --tail=200

# Control API logs
docker compose logs -f control-api

# Discovery logs
docker compose logs -f discovery-worker

# Restart UI
docker compose restart web-ui

# Stop while preserving state
docker compose down
```

Windows PowerShell users can also run:

```powershell
.\scripts\start.ps1
```

---

## Repository layout

```text
sentinelview/
├── agents/
│   └── sentinel-agent/          Go managed agent
├── services/
│   ├── control-api/             FastAPI control plane
│   └── web-ui/                  First-party operations UI
├── deploy/
│   ├── prometheus/
│   ├── grafana/
│   ├── blackbox/
│   └── loki/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── UI_GUIDE.md
│   ├── OPERATIONS.md
│   ├── AGENT_DEPLOYMENT.md
│   ├── API.md
│   ├── SECURITY.md
│   ├── GRAFANA.md
│   └── ROADMAP.md
├── scripts/
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## What is intentionally not claimed in v0.3.0

The following remain future work or partial foundations:

- thousands of vendor-specific monitoring plugins;
- full LLDP/CDP automatic topology inference;
- production notification dispatch and escalation engine;
- recurring maintenance scheduler logic;
- OIDC/LDAP/SAML;
- distributed remote collectors and offline buffering;
- HA control plane and PostgreSQL HA;
- signed staged automatic agent upgrades with canary/rollback;
- MSI/DEB/RPM release packages (one-command service installation is implemented);
- mature service/application discovery for databases and middleware;
- authoritative pre-v0.3.0 availability history;
- complete Checkmk Enterprise/Ultimate parity.

These limitations are documented so a demo does not depend on fake functionality.

---

## Recommended next milestones

The next engineering order is:

1. v0.3.1: stronger rule inheritance, maintenance behavior, notification dispatch and SNMP credential management.
2. v0.3.2: LLDP/CDP topology inference, interface-focused network views, APC UPS and Vertiv integration packs.
3. v0.3.3: OIDC/RBAC hardening, reporting, SLA refinement and signed artifacts.
4. v0.4.0: remote collectors, multi-site distributed monitoring, buffering and HA-oriented deployment.

See `docs/ROADMAP.md` for detail.
