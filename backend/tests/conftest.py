import hashlib
import hmac
import json
import os
import tempfile
import time
from urllib.parse import urlencode

TEST_TOKEN = "test-token:AA"

os.environ["TELEGRAM_BOT_TOKEN"] = TEST_TOKEN
os.environ["ALLOWED_TELEGRAM_IDS"] = "123"
os.environ["MEDIA_DIR"] = tempfile.mkdtemp(prefix="rezka-media-")
os.environ["FRONTEND_DIR"] = "/nonexistent"
os.environ.pop("HEARTBEAT_URL", None)


def forge_init_data(user_id: int = 123, token: str = TEST_TOKEN, auth_date: int | None = None) -> str:
    user = json.dumps({"id": user_id, "first_name": "Test", "username": "t"}, separators=(",", ":"))
    data = {"auth_date": str(auth_date if auth_date is not None else int(time.time())), "user": user}
    check_string = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)
