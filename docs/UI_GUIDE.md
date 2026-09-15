# SentinelView v0.3.0 UI Guide

The first-party UI is available on port `3001` and is the primary operator interface.

## Navigation

### Monitor

- **Overview** — top-level host/service/problem/agent health, sites and recent events.
- **Hosts** — monitored assets with service/problem counts.
- **Services** — service-centric view across every host.
- **Problems** — active warning/critical conditions and acknowledgement.
- **Events** — discovery, agent and state-change event history.
- **Topology** — visual graph of devices and known edges.

### Manage

- **Discovery** — launch private CIDR scans and view progress/history.
- **Inventory** — asset metadata including IP, MAC, class, site, agent and SNMP state.
- **Agents** — one-command agent enrollment and lifecycle status.
- **Agent Policies** — collector enablement and collection/check-in intervals.

### Configure

- **Monitoring Rules** — CPU/RAM/disk/agent thresholds.
- **SNMP** — create generic SNMP monitoring targets.
- **Integrations** — implemented and planned integration packs.
- **Notifications** — notification channel configuration foundation.
- **Maintenance** — maintenance windows and SLA-exclusion metadata.

### Report

- **Availability & SLA** — current availability calculations and SLA targets.

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
- latest CPU, RAM, process and uptime telemetry;
- disk usage;
- CPU and memory historical charts from Prometheus;
- service state table;
- active problems;
- agent identity/version.

## Problem acknowledgement

Open Problems and click **Acknowledge**. The problem remains active while the condition is still bad but records the acknowledging user and time. It automatically resolves when the service returns to OK.

## Agent installation

Go to Agents and generate a short-lived one-command installer. Use the Control API LAN/DNS URL reachable by the endpoint, not `localhost`.

## Viewer/operator/admin behavior

- Viewer: read-oriented monitoring pages.
- Operator: write monitoring configuration and view audit log.
- Admin: user management plus all operator functions.

This role model is intentionally simple in v0.3.0. Granular per-site/per-object permissions are roadmap work.
