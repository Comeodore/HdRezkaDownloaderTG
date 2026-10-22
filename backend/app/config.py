from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")

    hdrezka_email: str = Field(default="", alias="HDREZKA_EMAIL")
    hdrezka_password: str = Field(default="", alias="HDREZKA_PASSWORD")
    hdrezka_origin: str = Field(default="https://rezka.fi", alias="HDREZKA_ORIGIN")

    allowed_ids_raw: str = Field(default="", alias="ALLOWED_TELEGRAM_IDS")
    mini_app_url: str = Field(default="https://rezka.comeodore.services", alias="MINI_APP_URL")
    notify: bool = Field(default=True, alias="NOTIFY_ON_FINISH")

    media_dir: str = Field(default="/storage/files/Media", alias="MEDIA_DIR")
    data_dir: str = Field(default="/app/data", alias="DATA_DIR")
    frontend_dir: str = Field(default="/app/static", alias="FRONTEND_DIR")
    samba_uid: int = Field(default=1000, alias="SAMBA_UID")
    samba_gid: int = Field(default=1000, alias="SAMBA_GID")

    user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        ),
        alias="USER_AGENT",
    )
    rezka_concurrency: int = 6
    download_concurrency: int = Field(default=2, alias="DOWNLOAD_CONCURRENCY")
    chunk_size: int = 1024 * 1024
    connect_timeout: int = 30
    read_timeout: int = 120
    max_retries: int = 4
    retry_delay: float = 5.0
    min_free_space: int = 2 * 1024**3

    init_data_ttl: int = Field(default=86400, alias="INIT_DATA_TTL")
    session_token_ttl: int = Field(default=43200, alias="SESSION_TOKEN_TTL")
    # Local testing only: treat requests without Telegram init data as this user.
    dev_fake_user_id: int = Field(default=0, alias="DEV_FAKE_USER_ID")

    @property
    def allowed_ids(self) -> set[int]:
        ids: set[int] = set()
        for part in self.allowed_ids_raw.replace(";", ",").split(","):
            part = part.strip()
            if part.lstrip("-").isdigit():
                ids.add(int(part))
        return ids


@lru_cache
def get_settings() -> Settings:
    return Settings()
