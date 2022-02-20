from __future__ import annotations

import logging

from pydantic import AnyUrl, BaseSettings, DirectoryPath, Field, SecretStr, validator

from typing import List, Optional

logger = logging.getLogger("nerddiary.tgbot.config")


class NerdDiaryTGBotConfig(BaseSettings):
    API_ID: SecretStr = Field(..., exclude=True)
    API_HASH: SecretStr = Field(..., exclude=True)
    BOT_TOKEN: SecretStr = Field(..., exclude=True)
    BOT_DEBUG: bool = Field(default=False, exclude=True)
    SESSION_NAME: str = Field(default="nerddy")
    SESSION_PATH: DirectoryPath = Field(default="./")
    SERVER: AnyUrl | None = Field(default=None)
    ADMINS: List[int] = Field(min_items=1)
    ALLOWED_USERS: Optional[List[int]] = Field(min_items=1)
    SESSION_UPDATE_TIMEOUT: float = 5

    @validator("SERVER")
    def server_port_must_be_correct(cls, v: AnyUrl):
        if v and v.port != "80" and v.port != "443":
            raise ValueError(f"Unexpected server port {v.port=}. Expecting 80 or 443")

        return v

    @validator("SERVER")
    def server_host_must_be_ip(cls, v: AnyUrl):
        if v and not v.host_type == "ipv4":
            raise ValueError(f"Unexpected server host {v.host_type=}. Expecting ipv4 address")

        return v

    class Config:
        title = "NerdDiary Telegram Bot Configuration"
        extra = "forbid"
        env_prefix = "NERDDY_TGBOT_"
        env_file = ".env"
        env_file_encoding = "utf-8"
