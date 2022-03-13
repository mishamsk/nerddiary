""" Session base abstracct model """

from __future__ import annotations

import asyncio
import datetime
import logging

from pydantic import ValidationError

from ...data.data import DataConnection, DataProvider, IncorrectPasswordKeyError
from ...error.error import NerdDiaryError, NerdDiaryErrorCode
from ...poll.poll import Poll
from ...poll.workflow import AddAnswerResult, PollWorkflow
from ...user.user import User
from ..schema import NotificationType, Schema, UserSessionSchema
from .status import UserSessionStatus

from typing import Any, Coroutine, Dict, Iterable, List, Set, Tuple

# from datetime import datetime


SESSION_DATA_CATEGORY = "SESSION"
CONFIG_DATA_CATEGORY = "CONFIG"


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

    async def unlock(self, password_or_key: str | bytes):
        if self.user_status > UserSessionStatus.LOCKED:
            return

        if self.user_status != UserSessionStatus.LOCKED:
            raise NerdDiaryError(
                NerdDiaryErrorCode.SESSION_INCORRECT_STATUS,
                ext_message="Session is not locked. Can't unlock",
            )

        if self._data_connection:
            raise NerdDiaryError(
                NerdDiaryErrorCode.SESSION_INTERNAL_ERROR_INCORRECT_STATE,
                ext_message="Data connection already existed when trying to unlock",
            )

        try:
            self._data_connection = self._session_spawner._data_provoider.get_connection(
                user_id=self.user_id, password_or_key=password_or_key
            )
        except IncorrectPasswordKeyError:
            raise NerdDiaryError(NerdDiaryErrorCode.SESSION_INCORRECT_PASSWORD_OR_KEY)

        new_status = UserSessionStatus.UNLOCKED
        # TODO: FULL deserialize and proper exception handling for those who uses this method
        if self._session_spawner._data_provoider.check_user_data_exist(self.user_id, category=CONFIG_DATA_CATEGORY):
            try:
                config = self._data_connection.get_user_data(category=CONFIG_DATA_CATEGORY)
                assert config

                self._user_config = User.parse_raw(config)
                new_status = UserSessionStatus.CONFIGURED
            except ValidationError:
                raise NerdDiaryError(NerdDiaryErrorCode.SESSION_DATA_PARSE_ERROR)

        await self._set_status(new_status=new_status)

    async def get_polls(self) -> List[Poll] | None:
        if not self.user_status >= UserSessionStatus.CONFIGURED:
            raise NerdDiaryError(
                NerdDiaryErrorCode.SESSION_INCORRECT_STATUS,
                "List of polls requested, but user has no configuration yet.",
            )

        return self._user_config.polls

    async def start_poll(self, poll_name: str) -> PollWorkflow:
        if not self.user_status >= UserSessionStatus.CONFIGURED:
            raise NerdDiaryError(
                NerdDiaryErrorCode.SESSION_INCORRECT_STATUS,
                f"Request to start poll <{poll_name}>, but user has no configuration yet.",
            )

        assert self._user_config

        poll = self._user_config._polls_dict.get(poll_name)
        if poll is None:
            raise NerdDiaryError(NerdDiaryErrorCode.SESSION_POLL_NOT_FOUND, poll_name)

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
            raise NerdDiaryError(NerdDiaryErrorCode.SESSION_POLL_RUN_ID_NOT_FOUND, poll_run_id)

        res = workflow.add_answer(answer=answer)
        match res:
            case AddAnswerResult.DELAY:
                # TODO: add delay job
                pass
            case AddAnswerResult.COMPLETED:
                # TODO: what are we doing on completion? probably nothing
                pass
            case AddAnswerResult.ERROR:
                raise NerdDiaryError(NerdDiaryErrorCode.SESSION_POLL_ANSWER_UNSUPPORTED_VALUE)

        return workflow

    async def set_config(self, config: str):
        if not self.user_status >= UserSessionStatus.UNLOCKED:
            raise NerdDiaryError(
                NerdDiaryErrorCode.SESSION_INCORRECT_STATUS,
                "Can't set config. Session is new or locked.",
            )

        try:
            self._user_config = User.parse_raw(config)
            await self._set_status(new_status=UserSessionStatus.CONFIGURED)
        except ValidationError:
            raise NerdDiaryError(NerdDiaryErrorCode.SESSION_INVALID_USER_CONFIGURATION)

    async def _set_status(self, new_status: UserSessionStatus):
        if self.user_status == new_status:
            return

        self._user_status = new_status
        await self._session_spawner.notify(
            type=NotificationType.SERVER_SESSION_UPDATE,
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

    async def get(self, user_id: str) -> UserSession:
        if user_id in self._sessions:
            return self._sessions[user_id]

        try:
            self._sessions[user_id] = await self._load_or_create_session(user_id)
            return self._sessions[user_id]
        except NerdDiaryError:
            self._logger.exception("Error getting session")
            raise

    async def close(self) -> None:
        for session in self._sessions.values():
            await session.close()

    async def init_sessions(self) -> None:
        sessions = {}

        for user_id in self._data_provoider.get_user_list():
            try:
                sessions[user_id] = await self._load_or_create_session(user_id)
            except NerdDiaryError as e:
                self._logger.warning(f"Failed to load session, skipping. Reason: {e!r}")

        self._sessions = sessions

        if len(self._sessions) > 0:
            to_notify: List[Coroutine[Any, Any, None]] = []
            for user_id, ses in self._sessions.items():
                to_notify.append(
                    self.notify(
                        NotificationType.SERVER_SESSION_UPDATE,
                        UserSessionSchema(user_id=user_id, user_status=ses.user_status),
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

        session_exists = self._data_provoider.check_user_data_exist(user_id=user_id)
        lock_exists = self._data_provoider.check_lock_exist(user_id)
        if session_exists and not lock_exists:
            raise NerdDiaryError(NerdDiaryErrorCode.SESSION_NO_LOCK)

        self._logger.debug(f"Creating session. {session_exists=}")
        user_status = UserSessionStatus.LOCKED if session_exists else UserSessionStatus.NEW
        session = UserSession(session_spawner=self, user_id=user_id, user_status=user_status)

        return session
