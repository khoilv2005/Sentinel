from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.credential_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secrets(values: dict[str, str]) -> str:
    payload = json.dumps(values, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_secrets(value: str) -> dict[str, str]:
    try:
        raw = _fernet().decrypt(value.encode("ascii"))
        data = json.loads(raw)
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("credential cannot be decrypted; verify SENTINEL_CREDENTIAL_SECRET") from exc
    if not isinstance(data, dict):
        raise ValueError("invalid encrypted credential payload")
    return {str(k): str(v) for k, v in data.items() if v is not None}
