""" Session base abstracct model """

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field, PrivateAttr

from ...data.data import DataConnection
from ...poll.workflow import PollWorkflow
from ...user.user import User

from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from ..job import UserJob


class UserSessionStatus(enum.IntFlag):
    NEW = 0
    LOCKED = 1
    CONFIG_EXIST = 2
    DATA_EXIST = 4


class UserSession(BaseModel):
    user_id: int
    user_status: UserSessionStatus = Field(default=UserSessionStatus.NEW)
    jobs: Dict[str, UserJob] = Field(default={})
    config: User | None = PrivateAttr(default=None)
    data_connection: DataConnection | None = PrivateAttr(default=None)
    active_polls: Dict[str, PollWorkflow] = PrivateAttr(default={})
    poll_last_timestamps: Dict[str, datetime] = PrivateAttr(default={})


# TODO: Change to SessionSpawner
class Session(BaseModel, ABC):
    name: str

    @abstractmethod
    async def create_session(self):
        pass

    @abstractmethod
    async def close_session(self):
        pass
