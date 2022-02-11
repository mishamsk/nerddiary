from __future__ import annotations

import logging

from pydantic import AnyUrl, BaseSettings, Field, SecretStr, validator

from typing import ClassVar, Generator, List, Optional

logger = logging.getLogger("nerddiary.tgbot.config")


class NerdDiaryTGBotConfig(BaseSettings):
    _config_file_path: ClassVar[str] = ""
    API_ID: SecretStr = Field(..., exclude=True)
    API_HASH: SecretStr = Field(..., exclude=True)
    BOT_TOKEN: SecretStr = Field(..., exclude=True)
    BOT_DEBUG: bool = Field(default=False, exclude=True)
    SESSION_NAME: str = Field(default="nerddy", exclude=True)
    SERVER: AnyUrl | None = Field(default=None, exclude=True)
    admins: List[int] = Field(min_items=1)
    allowed_users: Optional[List[int]] = Field(min_items=1)

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

    @classmethod
    def load_config(cls, config_file_path: str | None = None) -> Generator[NerdDiaryTGBotConfig, None, None]:
        if config_file_path:
            cls._config_file_path = config_file_path

        logger.debug(f"Reading config file at: {cls._config_file_path}")

        conf = None

        try:
            conf = cls.parse_file(cls._config_file_path)
            yield conf
        except OSError:
            logger.error(f"File at '{cls._config_file_path}' doesn't exist or can't be open")
            raise ValueError(f"File at '{cls._config_file_path}' doesn't exist or can't be open")
        finally:
            if conf:
                with open(cls._config_file_path, mode="w+") as f:
                    f.write(conf.json())
