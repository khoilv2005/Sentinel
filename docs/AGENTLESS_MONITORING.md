# Remote monitoring methods

> Legacy note: older SentinelView builds called this area **Agentless monitoring**. In v0.4 the operator-facing concept is simply **Monitoring**. The legacy `/api/v1/agentless/*` endpoints remain compatibility aliases while new clients should use `/api/v1/monitoring/*`.

SentinelView separates two questions clearly:

1. **Discovery** — what assets exist on an authorized network?
2. **Monitoring** — how should SentinelView collect health and performance from each asset?

Discovery enriches inventory identity only. It does not own runtime health state.

## Monitoring methods

- **Managed Sentinel Agent** — optional outbound agent for richer/high-frequency endpoint telemetry.
- **WinRM** — Windows CPU, memory, disks, uptime, process count and network counters through PowerShell/CIM.
- **SSH** — Linux/Unix CPU, memory, disks, uptime, process count and `/proc/net/dev` counters.
- **SNMP** — network, appliance, power and environmental polling. The operator configures SNMP as one monitoring method; `snmp_exporter` is an internal backend integration rather than a separate product workflow.
- **ICMP/blackbox** — reachability/synthetic probing through Prometheus Blackbox Exporter.

## Target workflow

Remote monitoring supports three assignment scopes:

1. `Selected IPs` — list an authorized CIDR and choose specific targets.
2. `Discovered hosts in CIDR` — assign monitoring only to assets already present in inventory.
3. `Entire CIDR` — explicitly add/monitor every usable address in the authorized private CIDR.

Targets created by an explicit monitoring assignment start with health state `unknown` until a monitoring method returns evidence. Public ranges remain rejected.

## Credentials

Passwords, SNMP communities and private keys are encrypted using `SENTINEL_CREDENTIAL_SECRET`. API responses never expose plaintext or ciphertext secrets.

Set a strong stable value before production use:

```text
SENTINEL_CREDENTIAL_SECRET=<random-long-secret>
```

Changing this value later makes existing credentials undecryptable, so rotate credentials deliberately.

## Collector worker

`collector-worker` is the Docker service that executes scheduled WinRM/SSH/SNMP assignments. The Python module remains `app.agentless_worker` temporarily for backward-compatible packaging.

Each monitoring assignment writes its own latest sample to `collector_telemetry_latest`, keyed by `monitor_id`. This prevents one method (for example SNMP) from overwriting a richer SSH/WinRM sample from the same asset.

During the v0.4 transition, the worker also maintains `agentless_telemetry_latest` as a compatibility aggregate for existing Host Detail and Prometheus metric export. Higher-information WinRM/SSH data is preferred over generic SNMP unless the preferred aggregate becomes stale.

An asset is not marked down because one monitoring method fails. Remote health is aggregated across enabled assignments; the asset becomes down only when every enabled remote method reaches the failure threshold and no managed agent is online.

## Windows prerequisites

The target must permit WinRM from the SentinelView collector network and the supplied account must have permission to query CIM/performance data. SentinelView does not automatically weaken target-side WinRM policy.

WinRM credential `options` can tune transport behavior for slower or higher-latency hosts. The defaults are a 30-second WS-Man operation timeout, a 45-second HTTP read timeout and one retry for a transient WS-Man operation timeout. Supported overrides are `operation_timeout_sec`, `read_timeout_sec` and `retries` (0–3); `read_timeout_sec` must be greater than `operation_timeout_sec`. For example:

```json
{
  "transport": "ntlm",
  "operation_timeout_sec": 45,
  "read_timeout_sec": 60,
  "retries": 1
}
```

Authentication, authorization and other transport failures are not silently retried as operation timeouts.

## SSH host keys

Strict host-key checking can be enabled with `{"strict_host_key": true}` in credential options. The default lab-friendly behavior accepts unknown host keys; production deployments should enable strict verification.
