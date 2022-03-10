""" Session base abstracct model """

from __future__ import annotations

import asyncio
import datetime
import enum
import logging

from pydantic import ValidationError

from ...data.data import DataConnection, DataProvider, IncorrectPasswordKeyError
from ...poll.poll import Poll
from ...poll.workflow import AddAnswerResult, PollWorkflow
from ...user.user import User
from ..schema import NotificationType, Schema, UserSessionSchema
from .status import UserSessionStatus

from typing import Any, Coroutine, Dict, Iterable, List, Set, Tuple

# from datetime import datetime


SESSION_DATA_CATEGORY = "SESSION"
CONFIG_DATA_CATEGORY = "CONFIG"


class SessionErrorType(enum.Enum):
    UNDEFINED = enum.auto()
    SESSION_NO_LOCK = enum.auto()
    DATA_PARSE_ERROR = enum.auto()
    SESSION_INCORRECT_STATUS = enum.auto()
    POLL_NOT_FOUND = enum.auto()
    POLL_ANSWER_UNSUPPORTED_VALUE = enum.auto()


class SessionError(Exception):
    def __init__(self, type: SessionErrorType = SessionErrorType.UNDEFINED) -> None:
        self.type = type
        super().__init__(type)

    def __str__(self) -> str:
        mes = ""
        match self.type:
            case SessionErrorType.SESSION_NO_LOCK:
                mes = "Data corruption: Session found but data lock is missing"
            case SessionErrorType.DATA_PARSE_ERROR:
                mes = "Data corruption: Error parsing session data"
            case SessionErrorType.SESSION_INCORRECT_STATUS:
                mes = "User has no configuration yet"
            case SessionErrorType.POLL_NOT_FOUND:
                mes = "Poll wasn't found"
            case SessionErrorType.POLL_ANSWER_UNSUPPORTED_VALUE:
                mes = "Unsupported value for a poll answer was provided"
            case _:
                mes = "Unspecified session error"

        return f"Session error: {mes}"


class UserSession:
    def __init__(self, session_spawner: SessionSpawner, user_id: str, user_status: UserSessionStatus) -> None:
        self._session_spawner = session_spawner
        self._user_id = user_id
        self._user_status = user_status
        self._user_config: User | None = None
        self._data_connection: DataConnection | None = None
        self._active_polls: Dict[str, PollWorkflow] = {}

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def user_status(self) -> UserSessionStatus:
        return self._user_status

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
        # TODO: FULL deserialize and proper exception handling for those who uses this method
        if self._session_spawner._data_provoider.check_user_data_exist(self.user_id, category=CONFIG_DATA_CATEGORY):
            try:
                config = self._data_connection.get_user_data(category=CONFIG_DATA_CATEGORY)
                assert config

                self._user_config = User.parse_raw(config)
                new_status = UserSessionStatus.CONFIGURED
            except ValidationError:
                raise SessionError(SessionErrorType.DATA_PARSE_ERROR)

        await self._set_status(new_status=new_status)

        return True

    async def get_polls(self) -> List[Poll] | None:
        if not self.user_status >= UserSessionStatus.CONFIGURED:
            raise SessionError(SessionErrorType.SESSION_INCORRECT_STATUS)

        return self._user_config.polls

    async def start_poll(self, poll_name: str) -> PollWorkflow:
        if not self.user_status >= UserSessionStatus.CONFIGURED:
            raise SessionError(SessionErrorType.SESSION_INCORRECT_STATUS)

        assert self._user_config

        poll = self._user_config._polls_dict.get(poll_name)
        if poll is None:
            raise SessionError(SessionErrorType.POLL_NOT_FOUND)

        if poll.once_per_day:
            # TODO: also check current active
            logs = self._data_connection.get_last_n_logs(poll_code=poll.poll_name, count=1)
            if logs:
                log = logs[0][1]
                last_poll_start_timestamp = PollWorkflow.get_poll_start_timestamp_from_saved_data(log)

                if last_poll_start_timestamp.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) == datetime.datetime.now(self._user_config.timezone).replace(
                    hour=0, minute=0, second=0, microsecond=0
                ):
                    # TODO: return workflow initialized with last row id and data (edit mode)
                    pass

        workflow = PollWorkflow(poll=poll, user=self._user_config)
        self._active_polls[workflow.poll_run_id] = workflow
        return workflow

    async def add_poll_answer(self, poll_run_id: str, answer: str) -> PollWorkflow:

        workflow = self._active_polls.get(poll_run_id)
        if workflow is None:
            raise SessionError(SessionErrorType.POLL_NOT_FOUND)

        res = workflow.add_answer(answer=answer)
        match res:
            case AddAnswerResult.DELAY:
                # TODO: add delay job
                pass
            case AddAnswerResult.COMPLETED:
                # TODO: what are we doing on completion? probably nothing
                pass
            case AddAnswerResult.ERROR:
                raise SessionError(SessionErrorType.POLL_ANSWER_UNSUPPORTED_VALUE)

        return workflow

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

        self._user_status = new_status
        await self._session_spawner.notify(
            type=NotificationType.SESSION_UPDATE,
            data=UserSessionSchema(
                user_id=self.user_id, user_status=self.user_status, key=self._data_connection.key.decode()
            ),
        )

    # TODO: full serialization
    async def close(self):
        self._session_spawner._logger.debug("Closing session")

        if self._data_connection:
            if self._user_config:
                self._data_connection.store_user_data(
                    self._user_config.json(exclude_unset=True, ensure_ascii=False), category=CONFIG_DATA_CATEGORY
                )


class SessionSpawner:
    def __init__(
        self,
        data_provider: DataProvider,
        notification_queue: asyncio.Queue[Tuple[NotificationType, Schema | None, Set[str], str | None, str | None]],
        logger: logging.Logger = logging.getLogger(__name__),
    ) -> None:
        super().__init__()

        self._data_provoider = data_provider
        self._notification_queue = notification_queue
        self._sessions: Dict[str, UserSession] = {}
        self._logger = logger

    def get_all(self) -> Iterable[UserSession]:
        return self._sessions.values()

    async def get(self, user_id: str) -> UserSession | None:
        if user_id in self._sessions:
            return self._sessions[user_id]

        try:
            self._sessions[user_id] = await self._load_or_create_session(user_id)
            return self._sessions[user_id]
        except SessionError:
            self._logger.exception("Error getting session")
            return None

    async def close(self) -> None:
        for session in self._sessions.values():
            await session.close()

    async def init_sessions(self) -> None:
        sessions = {}

        for user_id in self._data_provoider.get_user_list():
            try:
                sessions[user_id] = await self._load_or_create_session(user_id)
            except SessionError as e:
                self._logger.warning(f"Failed to load session, skipping. Reason: {str(e)}")

        self._sessions = sessions

        if len(self._sessions) > 0:
            to_notify: List[Coroutine[Any, Any, None]] = []
            for user_id, ses in self._sessions.items():
                to_notify.append(
                    self.notify(
                        NotificationType.SESSION_UPDATE, UserSessionSchema(user_id=user_id, user_status=ses.user_status)
                    )
                )

            if to_notify:
                await asyncio.gather(*to_notify)

    async def notify(
        self,
        type: NotificationType,
        data: Schema | None = None,
        exclude: Set[str] = set(),
        source: str | None = None,
        target: str | None = None,
    ):
        await self._notification_queue.put((type, data, exclude, source, target))

    async def _load_or_create_session(self, user_id: str) -> UserSession:
        self._logger.debug("Loading session")

        session_exists = self._data_provoider.check_user_data_exist(user_id=user_id, category=SESSION_DATA_CATEGORY)
        lock_exists = self._data_provoider.check_lock_exist(user_id)
        if session_exists and not lock_exists:
            raise SessionError(SessionErrorType.SESSION_NO_LOCK)

        self._logger.debug(f"Creating session. {session_exists=}")
        user_status = UserSessionStatus.LOCKED if session_exists else UserSessionStatus.NEW
        session = UserSession(session_spawner=self, user_id=user_id, user_status=user_status)

        return session
