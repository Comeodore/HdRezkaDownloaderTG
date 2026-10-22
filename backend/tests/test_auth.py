import time

import pytest
from fastapi import HTTPException

from app.auth import issue_session_token, sign_media, validate_init_data, verify_media, verify_session_token
from app.config import get_settings
from tests.conftest import TEST_TOKEN, forge_init_data


def test_valid_init_data_returns_user():
    user = validate_init_data(forge_init_data(123), TEST_TOKEN, max_age=86400)
    assert user["id"] == 123


def test_tampered_hash_rejected():
    forged = forge_init_data(123)
    tampered = forged[:-4] + "0000"
    with pytest.raises(HTTPException) as exc:
        validate_init_data(tampered, TEST_TOKEN, max_age=86400)
    assert exc.value.status_code == 401


def test_wrong_bot_token_rejected():
    forged = forge_init_data(123, token="attacker-token")
    with pytest.raises(HTTPException) as exc:
        validate_init_data(forged, TEST_TOKEN, max_age=86400)
    assert exc.value.status_code == 401


def test_expired_init_data_rejected():
    stale = forge_init_data(123, auth_date=int(time.time()) - 100_000)
    with pytest.raises(HTTPException) as exc:
        validate_init_data(stale, TEST_TOKEN, max_age=86400)
    assert exc.value.status_code == 401


def test_session_token_round_trip():
    settings = get_settings()
    token = issue_session_token(123, settings)
    assert verify_session_token(token, settings) == 123


def test_session_token_tampered_rejected():
    settings = get_settings()
    token = issue_session_token(123, settings)
    with pytest.raises(HTTPException):
        verify_session_token(token[:-2] + "zz", settings)


def test_session_token_expired_rejected(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "session_token_ttl", -10)
    token = issue_session_token(123, settings)
    with pytest.raises(HTTPException):
        verify_session_token(token, settings)


def test_init_data_with_signature_field_still_validates():
    # Bot API 8+ adds an Ed25519 `signature` field; it is part of the HMAC check string
    import hashlib, hmac, json
    from urllib.parse import urlencode

    data = {"auth_date": str(int(time.time())), "signature": "abc", "user": json.dumps({"id": 123})}
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hmac.new(b"WebAppData", TEST_TOKEN.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    assert validate_init_data(urlencode(data), TEST_TOKEN, max_age=86400)["id"] == 123


def test_media_signature():
    settings = get_settings()
    sig = sign_media("https://statichdrezka.ac/p.jpg", settings)
    assert verify_media("https://statichdrezka.ac/p.jpg", sig, settings)
    assert not verify_media("https://evil.example/p.jpg", sig, settings)
