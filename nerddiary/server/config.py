from __future__ import annotations

import datetime
import logging

import pytz
from pydantic import BaseSettings, ValidationError, validator
from pydantic.fields import Field

from ..data.data import DataProvider
from ..primitive.timezone import TimeZone
from ..user.user import User

from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class NerdDiaryServerConfig(BaseSettings):

    default_timezone: TimeZone = Field(default=pytz.timezone("US/Eastern"))

    default_user: Optional[User] = Field(
        default=None, description="Optional default user config used to register a new user"
    )

    data_provider_name: str = Field(default="sqllite", description="Data provider to use to srote poll answers")
    """ Data provider to use to srote poll answers """

    data_provider_params: Dict[str, Any] | None = {"base_path": "data"}

    poll_timeout: Optional[datetime.timedelta] = Field(
        default=datetime.timedelta(hours=24),
        description="Timeout for an active poll expressed in timedelta (see https://pydantic-docs.helpmanual.io/usage/types/#datetime-types for supported formats). Timeout is reset every time a user input is received. Defaults to 24 hours",
    )
    """ Timeout for an active poll expressed in timedelta (see https://pydantic-docs.helpmanual.io/usage/types/#datetime-types for supported formats). Timeout is reset every time a user input is received. Defaults to 24 hours """

    @validator("data_provider_name")
    def data_provider_must_be_supported(cls, v):
        if v not in DataProvider.supported_providers:
            raise ValueError(f"Data provider <{v}> is not supported")

        return v

    @validator("data_provider_params")
    def data_provider_params_must_be_supported(cls, v, values: Dict[str, Any]):
        if not DataProvider.validate_params(values["data_provider_name"], v):
            raise ValueError(f"Incorrect data provider params <{v}> for data provider <{values['data_provider_name']}>")

        return v

    class Config:
        title = "NerdDiary Configuration Model"
        extra = "forbid"
        env_prefix = "NERDDY_"
        env_file = ".env"
        env_file_encoding = "utf-8"

    @classmethod
    def load_config(cls, config: str) -> NerdDiaryServerConfig:

        logger.debug(f"Reading server config: {config}")

        try:
            return cls.parse_raw(config)
        except ValidationError:
            logger.error("Not a valid NerdDiary Server config")

            raise ValueError(f"Config string <{config}> is not a valid NerdDiary Server config")
