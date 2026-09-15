import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status

from .config import settings


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_enrollment_token() -> str:
    return "sv_enr_" + secrets.token_urlsafe(32)


def new_agent_token() -> str:
    return "sv_agt_" + secrets.token_urlsafe(40)


def new_agent_id() -> str:
    return "agt_" + secrets.token_hex(12)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    rounds = 240_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), rounds)
    return f"pbkdf2_sha256${rounds}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds_s, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds_s)
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value.encode("ascii"))


def create_session_token(username: str, role: str) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)
    payload = {
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(expires_at.timestamp()),
        "kind": "ui",
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(settings.session_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(signature)}", expires_at


def decode_session_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(settings.session_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_decode(signature), expected):
            raise ValueError("bad signature")
        payload = json.loads(_b64url_decode(body))
        if payload.get("kind") != "ui" or int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired session") from exc


def control_identity(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    if x_api_key and secrets.compare_digest(x_api_key, settings.api_key):
        return {"username": "api-key", "role": "admin", "auth": "api-key"}
    if authorization and authorization.lower().startswith("bearer "):
        payload = decode_session_token(authorization.split(" ", 1)[1].strip())
        return {"username": payload["sub"], "role": payload.get("role", "viewer"), "auth": "session"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")


def require_api_key(x_api_key: str | None = Header(default=None)):
    """Backward-compatible dependency for external automation using X-API-Key."""
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    return True


def require_write(identity: dict = Depends(control_identity)):
    if identity.get("role") not in {"admin", "operator"}:
        raise HTTPException(status_code=403, detail="write permission required")
    return identity


def require_roles(*roles: str):
    def dependency(identity: dict = Depends(control_identity)):
        if identity is None:
            raise HTTPException(status_code=401, detail="authentication required")
        if identity.get("role") not in roles:
            raise HTTPException(status_code=403, detail="insufficient permissions")
        return identity
    return dependency
