# SentinelView v0.3.0 UI Guide

The first-party UI is available on port `3001` and is the primary operator interface.

## Navigation

### Monitor

- **Overview** — top-level host/service/problem/agent health, sites and recent events.
- **Hosts** — monitored assets with service/problem counts.
- **Services** — service-centric view across every host.
- **Problems** — active warning/critical/suppressed conditions and acknowledgement.
- **Events** — discovery, agent and state-change event history.
- **Topology** — visual graph of devices and known edges.

### Manage

- **Discovery** — launch private CIDR scans and view progress/history.
- **Inventory** — asset metadata including IP, MAC, class, site, agent and SNMP state.
- **Agents** — optional one-command managed-agent enrollment and lifecycle status.
- **Agentless** — configure WinRM, SSH or SNMP monitoring for selected IPs, discovered hosts or an entire authorized private CIDR.
- **Agent Policies** — managed-agent collector enablement and collection/check-in intervals.

### Configure

- **Credentials** — encrypted WinRM, SSH and SNMP credential profiles.
- **Monitoring Rules** — CPU/RAM/disk/agent thresholds.
- **SNMP** — create generic SNMP monitoring targets.
- **Integrations** — implemented and planned integration packs.
- **Notifications** — webhook/Slack/Teams/Telegram/SMTP channels, test delivery and recent delivery state.
- **Maintenance** — host/site/global maintenance windows with problem-notification suppression and optional SLA exclusion.

### Report

- **Availability & SLA** — availability calculations and SLA targets with maintenance exclusions applied to the eligible denominator.

### Platform

- **Users & Roles** — local account management (admin only).
- **Audit Log** — administrative actions (admin/operator).
- **Settings** — platform feature state and advanced component links.

## Global search

Use the top-bar search or `Ctrl+K` to search hostnames/IPs and event messages.

## Host detail

Click a host from Hosts, Inventory, Services, Availability or Topology.

Host Detail includes:

- state and inventory metadata;
- latest CPU, RAM, process and uptime telemetry when a collector is configured;
- disk usage;
- CPU and memory historical charts from Prometheus;
- service state table;
- active problems;
- managed-agent identity/version when enrolled.

Performance telemetry can come from agentless WinRM/SSH/SNMP or from the optional managed Sentinel Agent.

## Problem acknowledgement and maintenance

Open Problems and click **Acknowledge**. The problem remains active while the condition is still bad but records the acknowledging user and time. It automatically resolves when the service returns to OK.

If a matching active maintenance window has **Suppress problem notifications** enabled, the underlying bad condition remains visible but the problem is placed into a suppressed state and notification delivery is not attempted. When the maintenance window ends while the condition is still bad, SentinelView returns the problem to open/acknowledged state and queues a post-maintenance transition.

## Notifications

Create a channel in **Configure -> Notifications** and provide channel-specific JSON configuration. Supported channel types are webhook, Slack, Microsoft Teams, Telegram and SMTP email.

The page exposes:

- configured channels;
- a **Test** action for a real delivery attempt;
- recent queued/sent/suppressed/failed delivery records;
- retry errors and attempt counts.

Sensitive channel configuration is encrypted at rest and redacted from API/UI responses.

## Availability & SLA

Availability is derived from recorded state-change events. A maintenance window with **Exclude from SLA accounting** enabled removes the overlapping interval from the denominator instead of counting that planned downtime as unavailable time.

## Agent installation

Go to Agents and generate a short-lived one-command installer. Use the Control API LAN/DNS URL reachable by the endpoint, not `localhost`.

The managed agent is optional; it is an enhanced monitoring path rather than a prerequisite for basic performance metrics.

## Viewer/operator/admin behavior

- Viewer: read-oriented monitoring pages.
- Operator: write monitoring configuration and view audit log.
- Admin: user management plus all operator functions.

Active bearer sessions re-check the current local user record on each authenticated request. Disabling a user invalidates the existing session and role changes take effect immediately.

This role model is intentionally simple in v0.3.0. Granular per-site/per-object permissions are roadmap work.
