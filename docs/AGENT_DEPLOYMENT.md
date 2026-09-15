# SentinelView v0.3.0 Agent Deployment

## Goal

The endpoint experience is designed to be similar to mature monitoring platforms: generate an enrollment command in the UI, run it once, and let the agent become an OS service.

## Windows

In SentinelView:

```text
Manage -> Agents -> Generate install command
```

Use a server URL reachable from the endpoint, for example:

```text
http://192.168.1.10:8080
```

Run the generated PowerShell command as Administrator.

The bootstrap process:

1. downloads `sentinel-agent-windows-amd64.exe`;
2. downloads the corresponding SHA-256 file;
3. verifies the binary hash;
4. calls `sentinel-agent.exe install` with the server/token/site/tags;
5. enrolls and stores the persistent agent configuration;
6. installs `SentinelViewAgent` as a Windows Service;
7. sets automatic startup;
8. starts the service.

The persistent directory is under Windows ProgramData and the binary is installed under Program Files according to the agent implementation.

Useful commands:

```powershell
sentinel-agent.exe status
sentinel-agent.exe diagnose
sentinel-agent.exe restart
sentinel-agent.exe uninstall
sentinel-agent.exe version
```

## Linux

The UI generates a command similar to:

```bash
curl -fsSL http://SENTINEL-SERVER:8080/install/linux.sh \
  | sudo sh -s -- --server http://SENTINEL-SERVER:8080 \
  --token sv_enr_xxx --site default --tags linux
```

The installer verifies SHA-256, enrolls the agent and installs/enables a systemd service.

## Agent policy

On check-in, the agent receives its current policy from SentinelView.

Default policy fields:

```text
telemetry_interval_seconds
checkin_interval_seconds
collect_cpu
collect_memory
collect_disk
collect_network
collect_process_count
```

Edit policies from the first-party UI. Policy versions increment when changed and endpoints receive the new configuration on check-in.

## Telemetry

Current managed-agent telemetry:

- CPU utilization;
- memory total/used/utilization;
- disk total/used/utilization per mount;
- network receive/transmit counters per interface;
- uptime;
- process count.

## Connectivity

Endpoint -> SentinelView requires outbound HTTP/HTTPS to the Control API URL.

No inbound Prometheus scrape port is required for managed-agent mode.

## Troubleshooting

Use:

```text
sentinel-agent status
sentinel-agent diagnose
```

Then verify:

```text
SentinelView UI -> Agents
SentinelView UI -> Hosts -> endpoint
Prometheus -> query sentinel_agent_up
```

## Packaging status

v0.3.0 implements a one-command bootstrap installer plus native service installation. MSI/DEB/RPM release packages are still planned.
