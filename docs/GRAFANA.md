# Grafana in SentinelView v0.4.0

Grafana is no longer the main SentinelView UI.

Use the first-party UI on port `3001` for:

- hosts;
- services;
- problems;
- discovery;
- agent management;
- monitoring rules;
- topology;
- inventory;
- maintenance;
- availability/SLA;
- users/audit/settings.

Grafana remains useful for:

- advanced PromQL exploration;
- custom dashboards;
- long historical analysis;
- ad-hoc correlations;
- future Loki/Tempo/Mimir workflows.

## Managed-agent metrics

Prometheus scrapes the central Control API and receives metrics including:

```text
sentinel_agent_up
sentinel_cpu_usage_percent
sentinel_memory_total_bytes
sentinel_memory_used_bytes
sentinel_memory_usage_percent
sentinel_disk_total_bytes
sentinel_disk_used_bytes
sentinel_disk_usage_percent
sentinel_network_receive_bytes_total
sentinel_network_transmit_bytes_total
sentinel_uptime_seconds
sentinel_process_count
```

The first-party Host Detail page queries Prometheus through the Control API for historical CPU/memory charts, so the browser does not query Prometheus directly.
