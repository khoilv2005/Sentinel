from app.security import require_api_key
from fastapi import HTTPException

def test_api_key_accepts_configured_key(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "api_key", "abc")
    assert require_api_key("abc") is True

def test_api_key_rejects_wrong_key(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "api_key", "abc")
    try:
        require_api_key("wrong")
        assert False
    except HTTPException as exc:
        assert exc.status_code == 401
