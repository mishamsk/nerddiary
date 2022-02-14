from __future__ import annotations

import logging

from pydantic import BaseSettings, ValidationError, stricturl
from pydantic.fields import Field

logger = logging.getLogger(__name__)


class NerdDiaryClientConfig(BaseSettings):
    server_uri: stricturl(tld_required=False, allowed_schemes={"ws"}) = Field(  # type:ignore # noqa:F821
        default="ws://server:80/api/v1/ws/"
    )

    rpc_call_timeout: int = Field(default=5, gt=1, lt=3600, description="Timeout for rpc calls")

    reconnect_timeout: int = Field(default=15, gt=1, lt=3600, description="Timeout for connection retries")

    max_connect_retries: int = Field(default=10, gt=1, lt=100, description="Maximum number of connection retries")

    class Config:
        title = "NerdDiary Configuration Model"
        extra = "forbid"
        env_prefix = "NERDDY_"
        env_file = ".env"
        env_file_encoding = "utf-8"

    @classmethod
    def load_config(cls, config: str) -> NerdDiaryClientConfig:

        logger.debug(f"Reading config: {config}")

        try:
            return cls.parse_raw(config)
        except ValidationError:
            logger.error("Not a valid NerdDiary Client config")

            raise ValueError(f"Config string <{config}> is not a valid NerdDiary Client config")
