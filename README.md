# SentinelView v0.3.0

SentinelView is a self-hosted infrastructure monitoring and observability platform designed around a **first-party operations UI**, optional outbound managed agents, agentless WinRM/SSH/SNMP collection, Prometheus-compatible metrics, PostgreSQL inventory, SNMP/blackbox integrations and Grafana for optional advanced analytics.

v0.3.0 changes the product model significantly: **SentinelView UI is now the primary interface**. Operators no longer need Grafana, Prometheus or Swagger for normal monitoring workflows.

> Scope statement: v0.3.0 is a substantial lab/development platform and CV-grade monitoring project. It is not a claim of feature-for-feature parity with the commercial editions of Checkmk, Zabbix, Datadog or Elastic. The repository clearly separates implemented features from roadmap items.

## What v0.3.0 includes

The first-party UI at `http://localhost:3001` includes:

- Overview dashboard with host/service/problem/agent health.
- Hosts table with state, site, OS, agent status, services and problem counts.
- Host detail with latest CPU/RAM/disk/process telemetry and Prometheus history charts.
- Service-centric monitoring view.
- Active Problems view with acknowledgement.
- Operational Events view.
- Network Discovery UI with live scan progress.
- Infrastructure Inventory.
- Managed Agent onboarding and one-command Windows/Linux installation.
- Agentless monitoring with WinRM, SSH and generic SNMP polling.
- Agentless target selection by selected IPs, discovered hosts or an entire authorized private CIDR.
- Encrypted credential profiles for agentless monitoring.
- Agent Policies with central interval/collector changes.
- Monitoring Rules UI for CPU, memory, disk and agent availability thresholds.
- Topology visualization.
- SNMP target management.
- Integration catalog.
- Notification channels with queued webhook/Slack/Teams/Telegram/SMTP delivery, retry state and test delivery.
- Maintenance windows that can suppress problem notifications and exclude maintenance time from SLA accounting.
- Availability and SLA definitions.
- Local users and roles (`admin`, `operator`, `viewer`) with live role/disable enforcement for active sessions.
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
                  /    |      |     \
                 /     |      |      \
                v      v      v       v
          PostgreSQL Prometheus Workers  Agent artifacts
           inventory    :9090   |       Windows/Linux
           config         |      |         
           events         v      +-- discovery
           problems     Grafana  +-- agentless WinRM/SSH/SNMP
           users        :3000    +-- notification delivery
                                      ^
                                      |
                              webhook/SMTP/etc.
```

### Control plane

FastAPI owns:

- inventory;
- discovery jobs;
- managed-agent enrollment and credentials;
- encrypted agentless credential profiles;
- latest endpoint telemetry;
- service-state derivation;
- problem lifecycle;
- monitoring rules;
- maintenance windows and suppression state;
- availability/SLA definitions and maintenance exclusions;
- notification channel configuration and delivery queue;
- local UI sessions and roles;
- audit events;
- topology metadata;
- installation artifacts.

### Collection plane

SentinelView supports two endpoint-monitoring modes:

1. **Agentless** — WinRM for Windows, SSH for Linux/Unix and SNMP for network/infrastructure devices. This is suitable for basic CPU/RAM/disk/uptime/process/network monitoring without installing the Sentinel agent.
2. **Managed Agent** — optional enhanced outbound telemetry for endpoints that need a dedicated agent lifecycle and centrally managed policy.

The `agentless-worker` executes scheduled polls and automatically feeds host state, service/problem state and Prometheus-compatible metrics. Managed agents send telemetry outbound to the Control API.

### Metrics plane

Prometheus scrapes the central SentinelView `/metrics` endpoint. Endpoint machines do **not** require inbound Prometheus access in managed-agent mode, and agentless targets are polled by SentinelView rather than scraped directly by Prometheus.

### Notification plane

Problem lifecycle transitions are persisted to `notification_deliveries`. The `notification-worker` sends pending deliveries through enabled channels with bounded retry. Active maintenance can suppress matching deliveries.

Supported channel types:

```text
webhook
slack
teams
telegram
email (SMTP)
```

Channel delivery configuration is encrypted at rest using the SentinelView credential encryption key; API responses redact sensitive fields.

### Visualization

SentinelView UI renders normal operations views itself. Grafana is still provisioned for advanced PromQL dashboards and long-form troubleshooting.

---

## Requirements

Recommended development/lab host:

- Windows 10/11 + Docker Desktop, or Linux with Docker Engine.
- Docker Compose v2.
- 8 GB RAM minimum; 16 GB+ recommended for comfortable use.
- Internet access on the first build so Docker can download images and Go modules.

You do **not** need Python, Go or Node installed on the host to run the containerized platform. GitHub CI independently builds/tests the Go agent and runs disposable WinRM, SSH and SNMP integration targets.

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
SENTINEL_CREDENTIAL_SECRET=
POSTGRES_PASSWORD=
SENTINEL_DB_URL=
GF_SECURITY_ADMIN_PASSWORD=
```

`POSTGRES_PASSWORD` and the password embedded in `SENTINEL_DB_URL` must match. The supplied `.env.example` uses matching placeholder values so a copied template can perform a clean first boot before you replace the placeholders.

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

### Grafana password on an existing volume

Grafana persists its admin credential in `grafana-data`. Changing `GF_SECURITY_ADMIN_PASSWORD` after Grafana has already initialized does not rotate that stored credential. To explicitly rotate it on Windows:

```powershell
.\scripts\reset-grafana-admin.ps1 -Password 'your-new-password'
```

Do not delete the Grafana volume merely to apply a password change unless its stored state is disposable.

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

Discovery itself provides reachability and inventory. Performance telemetry can then come from either an agentless integration or the optional managed agent.

### 4. Enable agentless monitoring

Open:

```text
Configure -> Credentials
Manage -> Agentless
```

Create the appropriate credential profile and choose one of:

```text
WinRM  -> Windows
SSH    -> Linux/Unix
SNMP   -> network/infrastructure devices
```

Agentless scope can be:

```text
Selected IPs
Discovered hosts in CIDR
Entire private CIDR
```

For a `/24`, SentinelView can enumerate 254 usable addresses. Only monitor ranges and endpoints you are authorized to access.

### 5. Optional: install a Windows/Linux agent

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

### 6. Observe metrics

After collection intervals:

```text
Hosts -> <host>
```

can display:

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
WINRM/SSH/SNMP monitoring
CPU utilization
Memory utilization
Disk C:\
Process count
Interface Ethernet
```

`Problems` stores current warning/critical conditions. Operators can acknowledge active problems. A matching active maintenance window can place a problem into a suppressed state while the underlying condition remains active.

`Events` records discovery, enrollment and state-change events.

`Topology` renders known topology edges and all monitored nodes.

### Manage

`Discovery` starts private CIDR scans and displays progress/history.

`Inventory` shows IP, MAC, vendor/model, class, site, agent and SNMP state.

`Agents` implements Fleet-style managed-agent enrollment.

`Agentless` configures WinRM/SSH/SNMP monitoring for selected addresses, discovered hosts or an entire private CIDR.

`Agent Policies` centrally control managed-agent telemetry/check-in intervals and collectors.

### Configure

`Credentials` stores encrypted WinRM, SSH and SNMP credential profiles. API responses never return their plaintext secrets.

`Monitoring Rules` control service thresholds used by the first-party UI problem engine.

Default rules are seeded for:

```text
CPU utilization       warning 80% / critical 95%
Memory utilization    warning 85% / critical 95%
Disk utilization      warning 85% / critical 95%
Managed agent         critical when unavailable
```

Multiple rules may intentionally use the same metric; bootstrap defaults are identified by rule name so duplicate metric rules do not break startup.

`SNMP` manages Prometheus/snmp_exporter targets.

`Integrations` shows implemented and planned integration packs.

`Notifications` manages webhook, Slack, Teams, Telegram and SMTP channels. Problem open/escalation/recovery transitions are queued automatically; operators can test a channel and inspect recent delivery status. Failed deliveries retry with bounded exponential backoff.

`Maintenance` creates global, site or host windows. A window can suppress problem notifications and/or exclude its interval from SLA availability accounting.

### Report

`Availability & SLA` calculates availability using state-change events and removes maintenance intervals marked `exclude_from_sla` from the eligible denominator. Historical accuracy begins from recorded state transitions onward; old databases do not magically gain pre-upgrade history.

### Platform

`Users & Roles` manages local users:

- `admin`: platform administration;
- `operator`: monitoring operations and write actions;
- `viewer`: read-oriented UI access.

Bearer sessions re-check the local user record on every authenticated request, so disabling an account invalidates its existing session and role changes take effect without waiting for token expiry.

`Audit Log` records important administrative actions.

`Settings` shows platform configuration and advanced component links.

---

## Managed agent architecture

Managed Agent is an optional enhanced monitoring mode and uses an outbound architecture:

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

## Agentless architecture

The `agentless-worker` reads enabled monitor assignments from PostgreSQL and polls targets concurrently.

```text
Windows target -> WinRM/CIM --+
Linux target   -> SSH ---------+-> agentless-worker -> PostgreSQL -> /metrics -> Prometheus
SNMP target    -> SNMP --------+                         |
                                                       +-> Services / Problems / UI
```

After three consecutive collection failures, an assigned device can transition down; a successful poll clears the failure count and returns it up. The worker calls the problem engine after successful and failed polling transitions so state changes do not depend on a browser page being opened.

See `docs/AGENTLESS_MONITORING.md`.

---

## SNMP

SNMP targets are stored in SentinelView inventory and exported through HTTP service discovery:

```text
Device -> snmp_exporter -> Prometheus
```

Agentless generic SNMP polling additionally provides direct basic collection such as sysName/sysUpTime and supported HOST-RESOURCES data.

Vendor-specific packs (APC, Vertiv, Cisco/Fortinet/MikroTik depth, etc.) remain explicit roadmap work rather than simulated support.

---

## Problems, maintenance and notifications

SentinelView currently has complementary layers:

1. **First-party problem engine**: derives current services/problems from latest control-plane telemetry and monitoring rules.
2. **Maintenance engine**: matches global/site/device windows, suppresses requested problem notifications and excludes requested intervals from SLA accounting.
3. **Notification delivery engine**: creates persistent delivery records for lifecycle transitions and sends them asynchronously through the notification worker.
4. **Prometheus rule files**: provide Prometheus-native alert expressions for advanced monitoring workflows.

The notification engine is intentionally simpler than enterprise on-call products: policy trees, calendars, multi-step escalation chains and Alertmanager-compatible routing remain future work.

---

## Authentication

v0.3.0 introduces local UI session authentication.

The browser sends a signed bearer session token to the Control API through the UI reverse proxy. The signed token establishes identity, while current user enabled/role state is re-read from PostgreSQL for authorization.

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

## Upgrade notes

The project continues to add new tables rather than altering the original managed-agent tables where possible, so `Base.metadata.create_all()` can create additive schema in an existing lab database.

Current UI/operations tables include:

```text
problems
audit_events
maintenance_windows
notification_channels
notification_deliveries
sla_definitions
local_users
credential_profiles
agentless_monitors
agentless_telemetry_latest
```

Existing devices, scans, managed agents, policies and telemetry remain intact.

Because this project has not yet introduced Alembic migrations, take a database backup before non-trivial upgrades. Formal schema migrations are still a roadmap item.

---

## Development and tests

### API tests

```bash
PYTHONPATH=services/control-api \
SENTINEL_DB_URL=sqlite:////tmp/sentinel-test.db \
pytest -q services/control-api/tests
```

The regression suite includes bootstrap duplicate-rule handling, live bearer-session role/disable behavior, encrypted notification configuration, notification delivery, maintenance suppression, SLA exclusion and full `/24` agentless assignment tests.

### UI syntax

```bash
node --check services/web-ui/js/api.js
node --check services/web-ui/js/ui.js
node --check services/web-ui/js/app.js
node --check services/web-ui/js/runtime-enhancements.js
```

### Configuration validation

```bash
pip install pyyaml
python scripts/validate-config.py
```

### Go agent

Requires Go 1.25+ when building directly on a developer host:

```bash
cd agents/sentinel-agent
go mod tidy
go mod download all
go mod verify
go test ./...
```

Go is **not** required on the host to run SentinelView through Docker. GitHub CI installs Go 1.25 and verifies/cross-compiles the Linux and Windows agent artifacts independently.

### Integration workflow

`.github/workflows/integration.yml` provides disposable external-condition coverage:

- clean no-cache Docker application build on a GitHub-hosted Linux runner;
- real OpenSSH target and real SNMP daemon collection;
- three-failure agentless state transition followed by successful SSH recovery;
- real WinRM/CIM collection on a disposable Windows GitHub runner.

These tests are designed to close environment-dependent validation gaps without requiring permanent lab credentials or external hosts.

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

# Agentless logs
docker compose logs -f agentless-worker

# Notification delivery logs
docker compose logs -f notification-worker

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
│   ├── control-api/             FastAPI control plane/workers
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
│   ├── AGENTLESS_MONITORING.md
│   ├── API.md
│   ├── SECURITY.md
│   ├── GRAFANA.md
│   └── ROADMAP.md
├── qa/
│   └── integration/             Disposable real-target integration checks
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
- enterprise notification policy trees, on-call scheduling and multi-stage escalation;
- recurring maintenance recurrence rules beyond explicit start/end windows;
- OIDC/LDAP/SAML;
- distributed remote collectors and offline buffering;
- HA control plane and PostgreSQL HA;
- signed staged automatic agent upgrades with canary/rollback;
- MSI/DEB/RPM release packages (one-command service installation is implemented);
- mature service/application discovery for databases and middleware;
- authoritative availability history before state-transition recording began;
- complete Checkmk Enterprise/Ultimate parity.

These limitations are documented so a demo does not depend on fake functionality.

---

## Recommended next milestones

The next engineering order is:

1. v0.3.1: formal schema migrations, stronger rule inheritance, SNMP credential management and notification routing policies.
2. v0.3.2: LLDP/CDP topology inference, interface-focused network views, APC UPS and Vertiv integration packs.
3. v0.3.3: OIDC/RBAC hardening, reporting refinement, signed artifacts and release packaging.
4. v0.4.0: remote collectors, multi-site distributed monitoring, buffering and HA-oriented deployment.

See `docs/ROADMAP.md` for detail.
