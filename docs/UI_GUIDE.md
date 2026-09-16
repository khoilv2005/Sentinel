# SentinelView unified UI guide

The first-party UI is available on port `3001` and is the primary operator interface.

SentinelView now groups screens by operator workflow instead of exposing every backend implementation as a separate product feature.

## Primary navigation

### Monitor

- **Dashboard** — top-level asset/service/problem/agent health, sites and recent events.
- **Assets** — canonical inventory and monitoring view for discovered, manually added and managed infrastructure.
- **Problems** — active warning/critical/suppressed conditions and acknowledgement.
- **Operational Events** — discovery observations, monitoring polls and runtime state changes.

### Configure

- **Monitoring** — choose how SentinelView collects data from an asset.
- **Alerts** — thresholds, notification delivery and maintenance behavior.

### Report

- **Availability & SLA** — availability calculations and SLA targets with maintenance exclusions applied to the eligible denominator.

### Platform

- **Access** — local users and roles (admin only).
- **Audit** — administrative/configuration actions.
- **Settings** — platform feature state, component links and capability catalog.

## Asset views

The **Assets** area has four sub-views:

- **All assets** — merged host/inventory view with identity, health, service/problem counts and monitoring state.
- **Services** — service-centric view across assets.
- **Topology** — visual graph of assets and known edges.
- **Discovery** — private-CIDR inventory discovery and scan history.

Discovery answers **what assets exist?** It enriches inventory metadata but does not decide runtime health. A discovery miss no longer marks an asset down.

The old `Inventory` route redirects to Assets.

## Monitoring views

The **Monitoring** area has four sub-views:

- **Remote methods** — WinRM, SSH and SNMP assignments.
- **Managed Agent** — optional outbound Sentinel Agent enrollment and lifecycle status.
- **Credentials** — encrypted WinRM, SSH and SNMP credential profiles.
- **Agent settings** — managed-agent collection/check-in policy.

The old top-level concepts `Agentless` and `SNMP` are no longer separate product areas. SNMP is simply one Monitoring method; `snmp_exporter` remains an internal backend integration for Prometheus-native modules.

Remote monitoring supports:

1. selected IPs;
2. discovered assets in a CIDR;
3. an explicitly selected entire private CIDR.

## Alert views

The **Alerts** area has three sub-views:

- **Rules** — thresholds used to derive Services and Problems.
- **Notifications** — webhook/Slack/Teams/Telegram/SMTP channels, test delivery and recent delivery state.
- **Maintenance** — host/site/global windows with problem-notification suppression and optional SLA exclusion.

The SentinelView Control API is the single alert-evaluation source. Prometheus stores history and serves queries; it does not keep a competing set of alert thresholds.

## Global search

Use the top-bar search or `Ctrl+K` to search asset hostnames/IPs and operational event messages.

## Asset detail

Click an asset from All assets, Services, Availability or Topology.

Asset Detail includes:

- identity/inventory metadata;
- latest CPU, RAM, process and uptime telemetry when a collector is configured;
- disk usage;
- CPU and memory historical charts from Prometheus;
- service state table;
- active problems;
- managed-agent identity/version when enrolled.

Performance telemetry can come from WinRM/SSH/SNMP or from the optional managed Sentinel Agent.

## Health model

The asset reachability state remains `up`, `down` or `unknown`; the UI may display **degraded** when an asset is reachable but has active unhealthy services/problems.

One failed remote monitoring method does not make the entire asset down while another configured method is healthy. The collector layer aggregates evidence across enabled methods.

## Problem acknowledgement and maintenance

Open Problems and click **Acknowledge**. The problem remains active while the condition is still bad but records the acknowledging user and time. It automatically resolves when the service returns to OK.

If a matching active maintenance window has **Suppress problem notifications** enabled, the underlying bad condition remains visible but the problem is placed into a suppressed state and notification delivery is not attempted. When the maintenance window ends while the condition is still bad, SentinelView returns the problem to open/acknowledged state and queues a post-maintenance transition.

## Notifications

Open **Configure -> Alerts -> Notifications** and create a channel. Supported channel types are webhook, Slack, Microsoft Teams, Telegram and SMTP email.

The page exposes:

- configured channels;
- a **Test** action for a real delivery attempt;
- recent queued/sent/suppressed/failed delivery records;
- retry errors and attempt counts.

Sensitive channel configuration is encrypted at rest and redacted from API/UI responses.

## Availability & SLA

Availability is derived from recorded state-change events. A maintenance window with **Exclude from SLA accounting** enabled removes the overlapping interval from the denominator instead of counting that planned downtime as unavailable time.

## Managed Agent installation

Open **Configure -> Monitoring -> Managed Agent** and generate a short-lived one-command installer. Use the Control API LAN/DNS URL reachable by the endpoint, not `localhost` unless the endpoint is the same machine.

The managed agent is optional; it is an enhanced monitoring method rather than a prerequisite for basic performance metrics.

## Operational Events versus Audit

- **Operational Events** answer: what happened to the infrastructure/runtime?
- **Audit** answers: who changed SentinelView configuration or access?

They are intentionally separate records.

## Viewer/operator/admin behavior

- Viewer: read-oriented monitoring pages.
- Operator: write monitoring configuration and view audit.
- Admin: user management plus all operator functions.

Active bearer sessions re-check the current local user record on each authenticated request. Disabling a user invalidates the existing session and role changes take effect immediately.
