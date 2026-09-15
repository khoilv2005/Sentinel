# SentinelView Security Notes — v0.3.0

## Intended deployment

v0.3.0 is appropriate for a trusted lab or management VLAN. Before exposing it outside that environment, put SentinelView behind HTTPS and apply normal network segmentation/firewall controls.

## UI authentication

Local UI passwords are stored using PBKDF2-HMAC-SHA256 with per-password random salt.

The UI session is an HMAC-signed token with a configurable lifetime. Configure:

```text
SENTINEL_ADMIN_USER
SENTINEL_ADMIN_PASSWORD
SENTINEL_SESSION_SECRET
SENTINEL_SESSION_HOURS
```

Use a long random session secret.

## API key compatibility

`SENTINEL_API_KEY` remains available for external automation using `X-API-Key`. Treat it as an administrative credential.

Do not distribute this key to endpoint agents.

## Agent enrollment

Enrollment uses short-lived `sv_enr_*` tokens. The server stores only a SHA-256 hash of the enrollment token.

After enrollment, each endpoint receives a separate `sv_agt_*` agent credential. The database stores only the credential hash.

Revoking an agent invalidates that credential.

## Outbound model

Managed agents send check-ins/telemetry outbound to the Control API. Endpoint firewalls do not need a server-initiated connection to TCP/9123.

For production, serve the Control API over HTTPS so agent credentials and telemetry are protected in transit.

## Agent artifact integrity

Bootstrap installers download a `.sha256` alongside the agent and verify it before installation.

SHA-256 verifies integrity but is not equivalent to publisher code signing. Authenticode/GPG-signed release artifacts are roadmap work.

## SNMP

Prefer SNMPv3 for production devices. v1/v2c community strings are not encrypted in transit.

v0.3.0 stores SNMP profile identifiers, not a full production secret-management system. Vault-style encrypted credential management remains future work.

## Default secrets

Never keep the fallback development secrets for a serious deployment. Change at least:

```text
SENTINEL_API_KEY
SENTINEL_ADMIN_PASSWORD
SENTINEL_SESSION_SECRET
POSTGRES_PASSWORD
GF_SECURITY_ADMIN_PASSWORD
```

## Database

Do not publish PostgreSQL directly to untrusted networks. The default Compose file keeps PostgreSQL internal to the Compose network.

## Current security boundaries

Not yet implemented:

- OIDC/LDAP/SAML;
- per-site object-level authorization;
- mTLS agent identity;
- external secret vault integration;
- signed automatic agent update channel;
- CSRF-specific cookie controls (the current UI uses bearer tokens rather than session cookies).
