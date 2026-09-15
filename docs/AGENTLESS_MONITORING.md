# Agentless monitoring

SentinelView supports agentless monitoring as a first-class alternative to the managed Sentinel Agent.

## Collection methods

- **WinRM**: Windows CPU, memory, disks, uptime, process count and network counters through remote PowerShell/CIM.
- **SSH**: Linux/Unix CPU, memory, disks, uptime, process count and `/proc/net/dev` counters.
- **SNMP**: generic availability, sysName, sysUpTime and HOST-RESOURCES CPU polling. Prometheus `snmp_exporter` remains available for richer vendor-specific SNMP modules.
- **Sentinel Agent**: optional enhanced collection for higher-frequency and deeper endpoint telemetry.

## CIDR workflow

The Agentless page supports three scopes:

1. `Selected IPs` — load a range such as `192.168.1.0/24`, then tick only the hosts you want.
2. `Discovered hosts in CIDR` — apply a credential/method only to inventory entries already found by Discovery.
3. `Entire CIDR` — create monitoring assignments for every usable address in the authorized private CIDR.

Public ranges remain rejected by the same private-network guard used by Discovery.

## Credentials

Passwords, SNMP communities and private keys are encrypted using `SENTINEL_CREDENTIAL_SECRET`. API responses never expose plaintext or ciphertext secrets.

Set a strong stable value before production use:

```text
SENTINEL_CREDENTIAL_SECRET=<random-long-secret>
```

Changing this value later makes existing credentials undecryptable, so rotate credentials deliberately.

## Container worker

`agentless-worker` is a separate Docker service. It polls enabled assignments from PostgreSQL and executes collector jobs concurrently. Metrics are written to `agentless_telemetry_latest`; the existing Control API `/metrics` endpoint republishes them as SentinelView Prometheus metrics so current host graphs continue to work.

A target is marked down only after three consecutive collection failures to reduce transient flapping.

## Windows prerequisites

The target must permit WinRM from the SentinelView collector network and the supplied account must have permission to query CIM/performance data. SentinelView does not automatically weaken target-side WinRM policy.

## SSH host keys

Strict host-key checking can be enabled with `{"strict_host_key": true}` in credential options. The default lab-friendly behavior accepts unknown host keys; production deployments should enable strict verification.
