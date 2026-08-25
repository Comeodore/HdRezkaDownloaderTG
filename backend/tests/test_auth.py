import time

import pytest
from fastapi import HTTPException

from app.auth import issue_session_token, validate_init_data, verify_session_token
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
