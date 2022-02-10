from __future__ import annotations

import logging

from pydantic import AnyUrl, BaseSettings, Field, SecretStr, validator

from typing import Any, ClassVar, Dict, List, Optional

logger = logging.getLogger("nerddiary.tgbot.config")


class TGBotConfig(BaseSettings):
    _config_file_path: ClassVar[str] = ""
    API_ID: SecretStr = Field(..., exclude=True)
    API_HASH: SecretStr = Field(..., exclude=True)
    BOT_TOKEN: SecretStr = Field(..., exclude=True)
    BOT_DEBUG: bool = False
    SESSION_NAME: str = "Default"
    TEST_SERVER: AnyUrl | None = None
    TEST_MODE: bool = False
    TEST_PHONE: str = Field(default="9996628576", regex=r"^99966\d{5}$")
    admins: List[int] = Field(min_items=1)
    allowed_users: Optional[List[int]] = Field(min_items=1)

    @validator("TEST_MODE")
    def test_server_must_be_defined(cls, v, values: Dict[str, Any]):
        if v and values.get("TEST_SERVER") is None:
            raise ValueError("Test server address must be provided when test mode is enabled")

        return v

    @validator("TEST_SERVER")
    def test_server_port_must_be_correct(cls, v: AnyUrl):
        if v.port != "80" and v.port != "443":
            raise ValueError(f"Unexpected test server port {v.port=}. Expecting 80 or 443")

        return v

    @validator("TEST_SERVER")
    def test_server_host_must_be_ip(cls, v: AnyUrl):
        if not v.host_type == "ipv4":
            raise ValueError(f"Unexpected test server host {v.host_type=}. Expecting ipv4 address")

        return v

    class Config:
        title = "NerdDiary Telegram Bot Configuration"
        extra = "forbid"
        env_prefix = "NERDDY_TGBOT_"
        env_file = ".env"
        env_file_encoding = "utf-8"

    @classmethod
    def load_config(cls, config_file_path: str | None = None) -> TGBotConfig:
        if config_file_path:
            cls._config_file_path = config_file_path

        logger.debug(f"Reading config file at: {cls._config_file_path}")

        try:
            return cls.parse_file(cls._config_file_path)
        except OSError:
            logger.error(f"File at '{cls._config_file_path}' doesn't exist or can't be open")
            raise ValueError(f"File at '{cls._config_file_path}' doesn't exist or can't be open")
