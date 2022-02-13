""" Session base abstracct model """

from __future__ import annotations

import enum
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field, PrivateAttr

from ...data.data import DataConnection, DataProvider
from ...user.user import User
from ..schema import UserSessionSchema

from typing import TYPE_CHECKING, Any, Dict, Set, Tuple

# from datetime import datetime


# from ..poll.workflow import PollWorkflow


if TYPE_CHECKING:
    import asyncio

    from ..schema import NotificationType, Schema


@enum.unique
class UserSessionStatus(enum.IntFlag):
    NEW = 0
    LOCKED = 1
    UNLOCKED = 2
    CONFIG_EXIST = 4
    DATA_EXIST = 8


class UserSession(BaseModel):
    user_id: str
    user_status: UserSessionStatus = Field(default=UserSessionStatus.NEW, exclude=True)
    # active_polls: Dict[str, PollWorkflow] = PrivateAttr(default={})
    # poll_last_timestamps: Dict[str, datetime] = PrivateAttr(default={})
    _user_config: User | None = PrivateAttr(default=None)
    _data_connection: DataConnection | None = PrivateAttr(default=None)
    _session_spawner: SessionSpawner | None = PrivateAttr(default=None)

    async def unlock(self, password_or_key: str | bytes) -> bool:
        if self.user_status & UserSessionStatus.LOCKED:
            return True

        if self._data_connection:
            raise RuntimeError("Data connection already existed when trying to unlock")

        # TODO: Proper data exception handling
        self._data_connection = self._session_spawner._data_provoider.get_connection(
            user_id=self.user_id, password_or_key=password_or_key
        )

        new_status = UserSessionStatus.UNLOCKED
        if self._session_spawner._data_provoider.check_config_exist(self.user_id):
            new_status &= UserSessionStatus.CONFIG_EXIST

        if self._session_spawner._data_provoider.check_data_exist(self.user_id):
            new_status &= UserSessionStatus.DATA_EXIST

        await self.set_status(new_status=new_status)

        return True

    async def set_status(self, new_status: UserSessionStatus):
        if self.user_status == new_status:
            return

        self.user_status = new_status
        await self._session_spawner._notification_queue.put(
            (
                NotificationType.SESSION_UPDATE,
                UserSessionSchema(user_id=self.user_id, user_status=self.user_status, key=self._data_connection.key),
                Set(),
                None,
            )
        )

    async def close(self):
        await self._session_spawner.close_session(self)


class SessionCorruptionType(enum.Enum):
    UNDEFINED = enum.auto()
    SESSION_NO_LOCK = enum.auto()
    DATA_PARSE_ERROR = enum.auto()


class SessionCorruptionError(Exception):
    def __init__(self, type: SessionCorruptionType = SessionCorruptionType.UNDEFINED) -> None:
        self.type = type
        super().__init__(type)

    def __str__(self) -> str:
        mes = ""
        match self.type:
            case SessionCorruptionType.SESSION_NO_LOCK:
                mes = "Session found but data lock is missing"
            case SessionCorruptionType.DATA_PARSE_ERROR:
                mes = "Error parsing session data"
            case _:
                mes = "Unspecified session corruption"

        return f"Session corrupted: {mes}"


class SessionSpawner(ABC):
    def __init__(
        self,
        params: Dict[str, Any] | None,
        data_provider: DataProvider,
        notification_queue: asyncio.Queue[Tuple[NotificationType, Schema | None, Set[str], str | None]],
    ) -> None:
        super().__init__()

        self._data_provoider = data_provider
        self._raw_params = params
        self._notification_queue = notification_queue

    @abstractmethod
    async def create_session(self, user_id: str) -> UserSession:
        pass

    @abstractmethod
    async def close_session(self, session: UserSession):
        pass

    @abstractmethod
    async def load_sessions(self) -> Dict[str, UserSession]:
        pass
