# Remote monitoring (legacy filename)

> This file keeps its historical name temporarily so old links continue to work. In SentinelView v0.4 the product concept is **Remote monitoring**, not a separate “Agentless” product.

SentinelView can monitor an existing Asset without installing the managed Sentinel Agent.

## Asset-first workflow

The v0.4 invariant is:

```text
Discover or add Asset first
          ↓
Assign monitoring method
          ↓
Collect telemetry / derive health
```

Remote monitoring never creates inventory implicitly. If an IP is not already an Asset, Discovery or manual Add Asset must happen first.

## Collection methods

- **WinRM** — Windows CPU, memory, disks, uptime, process count and network counters through remote PowerShell/CIM.
- **SSH** — Linux/Unix CPU, memory, disks, uptime, process count and `/proc/net/dev` counters.
- **SNMP** — generic sysName/sysUpTime/HOST-RESOURCES style collection for network and infrastructure devices.
- **Sentinel Agent** — optional enhanced collection for higher-frequency/deeper endpoint telemetry; presented as another monitoring method rather than a separate product hierarchy.

## Target scopes

The compatibility API still accepts three scope names, but all of them operate on Assets already in inventory:

1. `selected` — explicitly selected existing Assets.
2. `discovered` — Assets inside the CIDR with previous observation evidence (`last_seen`).
3. `cidr_all` — all existing inventoried Assets inside the authorized private CIDR.

`cidr_all` no longer creates 254 placeholder Devices merely because a `/24` contains 254 usable addresses.

Public ranges remain rejected by the private-network guard.

## Credentials

Passwords, SNMP communities and private keys are encrypted using `SENTINEL_CREDENTIAL_SECRET`. API responses never expose plaintext or stored ciphertext secrets.

Set a strong stable value before production use:

```text
SENTINEL_CREDENTIAL_SECRET=<random-long-secret>
```

Changing this value later makes existing credentials undecryptable, so rotate deliberately.

## Collector worker

`collector-worker` is the Docker service that executes enabled WinRM/SSH/SNMP monitoring assignments concurrently.

The compatibility implementation module is still named `agentless_worker.py` during migration, but the operator-facing component is method-neutral.

Configure concurrency with:

```text
SENTINEL_COLLECTOR_WORKERS=24
```

The old `SENTINEL_AGENTLESS_WORKERS` environment variable remains a temporary fallback.

## Telemetry storage

Raw/latest remote telemetry is now stored per assignment in:

```text
monitoring_telemetry_latest
```

This fixes the v0.3 issue where one device-level row allowed SNMP/SSH/WinRM to overwrite each other.

For compatibility, SentinelView derives an aggregate `agentless_telemetry_latest` row for existing Prometheus/UI code. Host-oriented values prefer WinRM/SSH where available, while interface lists can prefer SNMP.

## Health model

Overall Asset health is derived from all configured monitoring methods:

```text
UP        healthy method(s), no failed method
DEGRADED  healthy and failed methods coexist
DOWN      failed method(s), no healthy method
UNKNOWN   no usable monitoring result yet
```

A remote assignment is treated as failed after three consecutive collection failures. A successful recovery clears its failure state. One failed monitoring method does not automatically force the entire Asset DOWN when another method is healthy.

Discovery does not own operational health.

## Windows prerequisites

The target must permit WinRM from the SentinelView collector network and the supplied account must have permission to query CIM/performance data. SentinelView does not automatically weaken target-side WinRM policy.

## SSH host keys

Strict host-key checking can be enabled with `{"strict_host_key": true}` in credential options. The default lab-friendly behavior accepts unknown host keys; production deployments should enable strict verification.

## SNMP migration note

The existing Prometheus `snmp_exporter` path remains available during v0.4 migration for compatibility and richer exporter modules. It is no longer treated as a separate top-level product feature. The target architecture exposes one operator concept: **SNMP monitoring method**.
