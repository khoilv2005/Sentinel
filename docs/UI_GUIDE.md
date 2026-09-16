# SentinelView v0.4 UI Guide

The first-party UI is available on port `3001` and is the primary operator interface.

v0.4 consolidates the UI around operator workflows. Legacy component routes still exist during migration, but they are presented as tabs inside the corresponding domain instead of separate top-level products.

## Navigation

### Monitor
- **Dashboard** — top-level asset/service/problem/agent health, sites and recent events.
- **Assets** — one infrastructure workspace. Tabs provide All assets, Services, Topology, Discover and Inventory details.
- **Problems** — active warning/critical/suppressed conditions and acknowledgement.
- **Operational Events** — discovery observations, collection state changes, agent events and runtime history.

### Manage / Configure
- **Monitoring** — how SentinelView collects data. Tabs expose Managed agent, Remote collectors (WinRM/SSH/SNMP), Credentials, Agent settings and the compatibility SNMP exporter view.
- **Alerts** — Rules, Notifications and Maintenance in one workflow.

### Report
- **Availability & SLA** — availability calculations and SLA targets with maintenance exclusions.

### Platform
- **Access** — local users and roles.
- **Audit** — administrative actions.
- **Settings** — platform state, advanced component links and capability catalog.

## Asset lifecycle

```text
Discover network OR add asset manually OR enroll managed agent
                         ↓
                       Asset
                         ↓
              assign monitoring method
                         ↓
              Services / Problems / SLA
```

Discovery finds and enriches Assets. Monitoring determines health/performance through Managed Agent, WinRM, SSH, SNMP or other configured methods. Enabling remote monitoring for an arbitrary IP no longer creates an inventory asset implicitly; add or discover it first.

## Global search

Use the top-bar search or `Ctrl+K` to search hostnames/IPs and event messages.

## Asset detail

Click an asset from Assets, Services, Availability or Topology. Asset Detail includes identity metadata, latest telemetry, disks, Prometheus history, service state, active problems and managed-agent identity when enrolled.

## Discovery

The Discover tab scans authorized private CIDRs and records identity/observation information such as IP, hostname, MAC, ports and inferred class. Discovery does **not** mark an asset operationally down simply because a later scan does not receive a response.

## Monitoring

### Managed agent
Generate short-lived installers and manage enrollment lifecycle.

### Remote collectors
Use WinRM for Windows, SSH for Linux/Unix and SNMP for network/infrastructure devices. Monitoring assignments only target existing Assets.

### Credentials
Secrets are encrypted before storage and are not returned by API/UI responses. A credential can also be created inline from the Remote collectors workflow.

### Agent settings
Managed-agent collection/check-in behavior remains centrally policy-driven.

### SNMP exporter
The compatibility SNMP exporter tab remains during migration. It is no longer a separate top-level product concept; SNMP is a monitoring method.

## Problem acknowledgement and maintenance

Problems can be acknowledged while active and resolve automatically on recovery. Matching maintenance can suppress problem notifications and optionally exclude time from SLA accounting.

## Notifications

Create a channel under **Alerts -> Notifications**. Supported types are webhook, Slack, Microsoft Teams, Telegram and SMTP email. Sensitive configuration is encrypted and redacted.

## Viewer/operator/admin behavior

- Viewer: read-oriented monitoring pages.
- Operator: write monitoring configuration and view audit log.
- Admin: user management plus all operator functions.
