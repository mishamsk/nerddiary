""" Session base abstracct model """

from __future__ import annotations

import asyncio
import enum
import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field, PrivateAttr, ValidationError

from ...data.data import DataConnection, DataProvider, IncorrectPasswordKeyError
from ...user.user import User
from ..schema import NotificationType, Schema, UserSessionSchema
from .status import UserSessionStatus

from typing import Any, Coroutine, Dict, Iterable, List, Set, Tuple

# from datetime import datetime


# from ..poll.workflow import PollWorkflow


class UserSession(BaseModel):
    user_id: str
    user_status: UserSessionStatus = Field(default=UserSessionStatus.NEW, exclude=True)
    # active_polls: Dict[str, PollWorkflow] = PrivateAttr(default={})
    # poll_last_timestamps: Dict[str, datetime] = PrivateAttr(default={})
    _user_config: User | None = PrivateAttr(default=None)
    _data_connection: DataConnection | None = PrivateAttr(default=None)
    _session_spawner: SessionSpawner | None = PrivateAttr(default=None)

    async def unlock(self, password_or_key: str | bytes) -> bool:
        if self.user_status > UserSessionStatus.LOCKED:
            return True

        if self._data_connection:
            raise RuntimeError("Data connection already existed when trying to unlock")

        try:
            self._data_connection = self._session_spawner._data_provoider.get_connection(
                user_id=self.user_id, password_or_key=password_or_key
            )
        except IncorrectPasswordKeyError:
            return False

        new_status = UserSessionStatus.UNLOCKED
        if self._session_spawner._data_provoider.check_config_exist(self.user_id):
            try:
                self._user_config = User.parse_raw(self._data_connection.load_config())  # type:ignore
                new_status = UserSessionStatus.CONFIGURED
            except ValidationError:
                pass

        await self._set_status(new_status=new_status)

        return True

    async def set_config(self, config: str) -> bool:
        try:
            self._user_config = User.parse_raw(config)
            await self._set_status(new_status=UserSessionStatus.CONFIGURED)
            return True
        except ValidationError:
            return False

    async def _set_status(self, new_status: UserSessionStatus):
        if self.user_status == new_status:
            return

        self.user_status = new_status
        await self._session_spawner._notify(
            type=NotificationType.SESSION_UPDATE,
            data=UserSessionSchema(
                user_id=self.user_id, user_status=self.user_status, key=self._data_connection.key.decode()
            ),
        )


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
        notification_queue: asyncio.Queue[Tuple[NotificationType, Schema | None, Set[str], str | None, str | None]],
        logger: logging.Logger = logging.getLogger(__name__),
    ) -> None:
        super().__init__()

        self._data_provoider = data_provider
        self._raw_params = params
        self._notification_queue = notification_queue
        self._sessions: Dict[str, UserSession] = {}
        self._logger = logger

    def get_all(self) -> Iterable[UserSession]:
        return self._sessions.values()

    async def get(self, user_id: str) -> UserSession | None:
        if user_id in self._sessions:
            return self._sessions[user_id]

        try:
            return await self._load_or_create_session(user_id)
        except SessionCorruptionError:
            self._logger.exception("Error getting session")
            return None

    async def close(self) -> None:
        for user_id in self._sessions:
            await self._close_session(user_id)

    async def load_sessions(self) -> None:
        self._sessions = await self._load_sessions()
        if len(self._sessions) > 0:
            to_notify: List[Coroutine[Any, Any, None]] = []
            for user_id, ses in self._sessions.items():
                to_notify.append(
                    self._notify(
                        NotificationType.SESSION_UPDATE, UserSessionSchema(user_id=user_id, user_status=ses.user_status)
                    )
                )

            if to_notify:
                await asyncio.gather(*to_notify)

    async def _notify(
        self,
        type: NotificationType,
        data: Schema = None,
        exclude: Set[str] = set(),
        source: str = None,
        target: str = None,
    ):
        await self._notification_queue.put((type, data, exclude, source, target))

    @abstractmethod
    async def _load_or_create_session(self, user_id: str) -> UserSession:
        pass

    @abstractmethod
    async def _close_session(self, user_id: str):
        pass

    @abstractmethod
    async def _load_sessions(self) -> Dict[str, UserSession]:
        pass
