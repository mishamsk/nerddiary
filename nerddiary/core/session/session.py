""" Session base abstracct model """

from __future__ import annotations

import asyncio
import enum
from abc import ABC, abstractmethod
from datetime import datetime

from apscheduler.schedulers.base import BaseScheduler
from pydantic import BaseModel, Field, PrivateAttr

from ..data.data import DataConnection, DataProvider
from ..poll.workflow import PollWorkflow
from ..user.user import User

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from ..job.job import UserJob


class UserSessionStatus(enum.IntFlag):
    NEW = 0
    LOCKED = 1
    CONFIG_EXIST = 2
    DATA_EXIST = 4


class UserSession(BaseModel):
    user_id: str
    jobs: Dict[str, UserJob] = Field(default={})
    user_status: UserSessionStatus = PrivateAttr(default=UserSessionStatus.NEW)
    config: User | None = PrivateAttr(default=None)
    data_connection: DataConnection | None = PrivateAttr(default=None)
    active_polls: Dict[str, PollWorkflow] = PrivateAttr(default={})
    poll_last_timestamps: Dict[str, datetime] = PrivateAttr(default={})
    _session_spawner: SessionSpawner | None = PrivateAttr(default=None)

    async def close(self):
        await self._session_spawner.close_session(self)


class SessionCorruptionType(enum.Enum):
    UNDEFINED = enum.auto()
    SESSION_NO_LOCK = enum.auto()


class SessionCorruptionError(Exception):
    def __init__(self, type: SessionCorruptionType = SessionCorruptionType.UNDEFINED) -> None:
        self.type = type
        super().__init__(type)

    def __str__(self) -> str:
        mes = ""
        match self.type:
            case SessionCorruptionType.SESSION_NO_LOCK:
                mes = "Session file found but data lock file is missing"
            case _:
                mes = "Unspecified session corruption"

        return f"Session corrupted: {mes}"


class SessionSpawner(ABC):
    def __init__(
        self,
        params: Dict[str, Any] | None,
        data_provider: DataProvider,
        scheduler: BaseScheduler,
        job_queue: asyncio.Queue,
    ) -> None:
        super().__init__()

        self._data_provoider = data_provider
        self._raw_params = params
        self._scheduler = scheduler
        self._job_queue = job_queue

    @abstractmethod
    async def create_session(self, user_id: str) -> UserSession:
        pass

    @abstractmethod
    async def close_session(self, session: UserSession):
        pass
