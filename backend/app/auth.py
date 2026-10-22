import base64
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, Query, status

from .config import Settings, get_settings
from .logging_conf import get_logger

logger = get_logger("auth")


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def _derived_key(bot_token: str, purpose: bytes) -> bytes:
    return hmac.new(_secret_key(bot_token), purpose, hashlib.sha256).digest()


def validate_init_data(init_data: str, bot_token: str, max_age: int) -> dict:
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True, keep_blank_values=True))
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed init data") from exc

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing hash")

    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    computed = hmac.new(_secret_key(bot_token), check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed.encode(), received_hash.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")

    auth_date = int(pairs.get("auth_date") or 0)
    if max_age > 0 and (time.time() - auth_date) > max_age:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Init data expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No user in init data")
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad user json") from exc
    if not isinstance(user, dict) or not str(user.get("id", "")).lstrip("-").isdigit():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad user")
    return user


def issue_session_token(user_id: int, settings: Settings) -> str:
    exp = int(time.time()) + settings.session_token_ttl
    payload = f"{user_id}:{exp}"
    sig = hmac.new(_derived_key(settings.bot_token, b"session"), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def verify_session_token(token: str, settings: Settings) -> int:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        user_id_str, exp_str, sig = raw.rsplit(":", 2)
        user_id, exp = int(user_id_str), int(exp_str)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad token") from exc

    expected = hmac.new(
        _derived_key(settings.bot_token, b"session"), f"{user_id_str}:{exp_str}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected.encode(), sig.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad token signature")
    if exp < time.time():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    return user_id


def sign_media(value: str, settings: Settings) -> str:
    """Short HMAC that lets the image proxy serve a URL without a per-session token.

    Stable signatures keep poster URLs identical across sessions, so the
    WebView and Cloudflare can cache them.
    """
    digest = hmac.new(_derived_key(settings.bot_token, b"media"), value.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest[:12]).decode().rstrip("=")


def verify_media(value: str, signature: str, settings: Settings) -> bool:
    # bytes, not str: compare_digest raises TypeError on non-ASCII strings
    return hmac.compare_digest(sign_media(value, settings).encode(), signature.encode())


def _check_allowlist(user_id: int, settings: Settings) -> None:
    if settings.dev_fake_user_id and user_id == settings.dev_fake_user_id:
        return
    if settings.allowed_ids and user_id not in settings.allowed_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")


async def require_user(
    x_telegram_init_data: str = Header(default=""),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not settings.bot_token:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Server not configured")
    if not x_telegram_init_data:
        if settings.dev_fake_user_id:
            return {"id": settings.dev_fake_user_id, "first_name": "Dev"}
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing init data")
    user = validate_init_data(x_telegram_init_data, settings.bot_token, settings.init_data_ttl)
    _check_allowlist(int(user["id"]), settings)
    return user


async def require_token_user(
    t: str = Query(default=""),
    settings: Settings = Depends(get_settings),
) -> int:
    if not t:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    user_id = verify_session_token(t, settings)
    _check_allowlist(user_id, settings)
    return user_id
