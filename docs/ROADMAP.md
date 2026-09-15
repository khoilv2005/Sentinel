# SentinelView Roadmap

## v0.3.0 — First-party Operations UI (implemented)

- first-party monitoring console;
- local UI login and basic roles;
- overview/hosts/host detail/services/problems/events;
- problem acknowledgement;
- discovery/inventory;
- managed agent onboarding and policies;
- monitoring rule UI;
- SNMP target UI;
- topology visualization;
- integration catalog;
- maintenance metadata;
- notification channel configuration foundation;
- availability/SLA UI;
- audit log;
- global search;
- Grafana demoted to advanced analytics.

## v0.3.1 — Monitoring behavior

- rule inheritance: global -> site -> group -> host -> service;
- more accurate duration-based problem evaluation;
- recurring maintenance schedules;
- notification routing/dispatch;
- encrypted SNMP/application credentials;
- service acknowledgement comments and ownership;
- better host/service grouping and saved views.

## v0.3.2 — Network/NOC depth

- LLDP/CDP ingestion;
- automatic topology edges;
- interface-focused views;
- bandwidth/error/drop service states;
- APC UPS integration pack;
- Vertiv environmental/cooling integration pack;
- Cisco/Fortinet/MikroTik integration depth;
- topology dependency-aware problem suppression.

## v0.3.3 — Enterprise identity/reporting

- OIDC/LDAP/SAML;
- granular RBAC and per-site scope;
- refined SLA/availability accounting;
- PDF/CSV scheduled reports;
- signed release artifacts;
- agent update inventory and manual central update.

## v0.4.0 — Distributed monitoring

- remote collectors;
- multi-site control plane;
- offline buffering/replay;
- central collector configuration;
- Mimir/remote-write production profile;
- HA-oriented deployment and Helm charts.

## Later

- Loki log workflows;
- OpenTelemetry/Alloy;
- Docker/Kubernetes;
- Proxmox/VMware/Hyper-V;
- database and middleware integration packs;
- staged/canary agent auto-update with rollback;
- mobile agent where platform APIs permit useful metrics.
