""" Session base abstracct model """

from __future__ import annotations

import asyncio
import datetime
import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from pydantic import ValidationError
from pydantic.json import pydantic_encoder

from ...data.data import DataConnection, DataProvider, IncorrectPasswordKeyError
from ...error.error import NerdDiaryError, NerdDiaryErrorCode
from ...poll.poll import Poll
from ...poll.workflow import AddAnswerResult, PollWorkflow
from ...user.user import User
from ..schema import NotificationType, PollBaseSchema, PollLogSchema, PollLogsSchema, Schema, UserSessionSchema
from .status import UserSessionStatus

from typing import Any, Coroutine, Dict, Iterable, List, Set, Tuple

# from datetime import datetime


ACTIVE_POLL_DATA_CATEGORY = "ACTIVE_POLL"
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
        if self._session_spawner._data_provoider.check_user_data_exist(self.user_id, category=CONFIG_DATA_CATEGORY):
            try:
                config = self._data_connection.get_user_data(category=CONFIG_DATA_CATEGORY)
                assert config

                self._user_config = User.parse_raw(config)
                if self._user_config.polls:
                    for poll in self._user_config.polls:
                        if poll.reminder_time:
                            self._session_spawner._scheduler.add_job(
                                func=self._session_spawner.notify,
                                trigger=CronTrigger(
                                    day_of_week=",".join(map(str, tuple(range(7)))),
                                    hour=poll.reminder_time.hour,
                                    minute=poll.reminder_time.minute,
                                    second=poll.reminder_time.second,
                                    timezone=poll.reminder_time.tzinfo,
                                ),
                                args=(
                                    NotificationType.SERVER_POLL_REMINDER,
                                    PollBaseSchema(user_id=self.user_id, poll_name=poll.poll_name),
                                ),
                                max_instances=1,  # type: ignore
                                coalesce=True,  # type: ignore
                                misfire_grace_time=10,  # type: ignore
                                name=f"{self._user_config.id}/{poll.poll_name}",
                            )

                new_status = UserSessionStatus.CONFIGURED
            except ValidationError:
                raise NerdDiaryError(NerdDiaryErrorCode.SESSION_DATA_PARSE_ERROR, ext_message=CONFIG_DATA_CATEGORY)

        if self._session_spawner._data_provoider.check_user_data_exist(
            self.user_id, category=ACTIVE_POLL_DATA_CATEGORY
        ):
            try:
                raw_data = self._data_connection.get_user_data(category=ACTIVE_POLL_DATA_CATEGORY)
                assert raw_data
                active_polls: Dict[str, Any] = json.loads(raw_data)

                self._active_polls = {i: PollWorkflow.from_dict(v) for i, v in active_polls.items()}

                for active_poll in self._active_polls.values():
                    if active_poll.delayed_until:
                        self._session_spawner._scheduler.add_job(
                            func=self._session_spawner.notify,
                            trigger=DateTrigger(run_date=active_poll.delayed_until),
                            args=(
                                NotificationType.SERVER_POLL_DELAY_PASSED,
                                active_poll.to_schema(),
                            ),
                            max_instances=1,  # type: ignore
                            coalesce=True,  # type: ignore
                            misfire_grace_time=10,  # type: ignore
                            name=f"{active_poll.poll_run_id}/{active_poll.current_question_code}",
                        )
            except ValidationError:
                raise NerdDiaryError(NerdDiaryErrorCode.SESSION_DATA_PARSE_ERROR, ext_message=ACTIVE_POLL_DATA_CATEGORY)

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
            for active_poll in self._active_polls.values():
                if active_poll.poll_name == poll_name:
                    raise NerdDiaryError(NerdDiaryErrorCode.SESSION_POLL_ALREADY_ACTIVE, poll_name)

            logs = self._data_connection.get_last_n_logs(poll_code=poll.poll_name, count=1)
            if logs:
                log_id, last_poll_ts, log = logs[0]

                if last_poll_ts.replace(hour=0, minute=0, second=0, microsecond=0) == datetime.datetime.now(
                    self._user_config.timezone
                ).replace(hour=0, minute=0, second=0, microsecond=0):
                    workflow = PollWorkflow.from_store_data(
                        poll=poll, user=self._user_config, log_id=log_id, poll_ts=last_poll_ts, log=log
                    )
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
                assert workflow.delayed_until

                self._session_spawner._scheduler.add_job(
                    func=self._session_spawner.notify,
                    trigger=DateTrigger(run_date=workflow.delayed_until),
                    args=(
                        NotificationType.SERVER_POLL_DELAY_PASSED,
                        workflow.to_schema(),
                    ),
                    max_instances=1,  # type: ignore
                    coalesce=True,  # type: ignore
                    misfire_grace_time=10,  # type: ignore
                    name=f"{poll_run_id}/{workflow.current_question_code}",
                )
            case AddAnswerResult.COMPLETED:
                pass
            case AddAnswerResult.ADDED:
                pass
            case AddAnswerResult.ERROR:
                raise NerdDiaryError(NerdDiaryErrorCode.SESSION_POLL_ANSWER_UNSUPPORTED_VALUE)

        return workflow

    async def close_poll(self, poll_run_id: str, save: bool):
        workflow = self._active_polls.pop(poll_run_id, None)
        if workflow is None:
            raise NerdDiaryError(NerdDiaryErrorCode.SESSION_POLL_RUN_ID_NOT_FOUND, poll_run_id)

        if save:
            if workflow.log_id is not None:
                self._data_connection.update_log(workflow.log_id, *workflow.get_save_data())
            else:
                self._data_connection.append_log(workflow.poll_name, *workflow.get_save_data())

    async def restart_poll(self, poll_run_id: str) -> PollWorkflow:
        workflow = self._active_polls.get(poll_run_id)
        if workflow is None:
            raise NerdDiaryError(NerdDiaryErrorCode.SESSION_POLL_RUN_ID_NOT_FOUND, poll_run_id)

        self._active_polls[poll_run_id] = new_workflow = PollWorkflow(
            poll=workflow._poll, user=workflow._user, poll_run_id=poll_run_id
        )

        return new_workflow

    async def get_all_poll_data(self) -> PollLogsSchema:
        if self.user_status <= UserSessionStatus.LOCKED:
            raise NerdDiaryError(
                NerdDiaryErrorCode.SESSION_INCORRECT_STATUS,
                "Requested data, but user session is either locked or not configured.",
            )

        ret = PollLogsSchema(logs=[])
        all_logs = self._data_connection.get_all_logs()

        for id, poll_name, poll_ts, data in all_logs:
            log = PollLogSchema(id=id, poll_name=poll_name, poll_ts=poll_ts, data=json.loads(data))
            ret.logs.append(log)

        return ret

    async def get_last_n_poll_logs(self) -> List[Dict[str, Any]] | None:
        if self.user_status < UserSessionStatus.CONFIGURED:
            return None

        ret = []
        all_logs = self._data_connection.get_all_logs()
        for id, poll_name, poll_ts, data in all_logs:
            d = {}
            d["id"] = id
            d["poll_name"] = poll_name
            d["poll_ts"] = poll_ts
            d["data"] = json.loads(data)
            ret.append(d)

        return ret

    async def close_all_polls(self, save: bool):
        for workflow in self._active_polls.values():
            if save:
                if workflow.log_id is not None:
                    self._data_connection.update_log(workflow.log_id, *workflow.get_save_data())
                else:
                    self._data_connection.append_log(workflow.poll_name, *workflow.get_save_data())

        self._active_polls.clear()

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

    async def close(self):
        self._session_spawner._logger.debug("Closing session")

        if self._data_connection:
            if self._user_config:
                self._data_connection.store_user_data(
                    self._user_config.json(exclude_unset=True, ensure_ascii=False), category=CONFIG_DATA_CATEGORY
                )
            if self._active_polls:
                self._data_connection.store_user_data(
                    json.dumps({i: v.to_dict() for i, v in self._active_polls.items()}, default=pydantic_encoder),
                    category=ACTIVE_POLL_DATA_CATEGORY,
                )


class SessionSpawner:
    def __init__(
        self,
        data_provider: DataProvider,
        notification_queue: asyncio.Queue[Tuple[NotificationType, Schema | None, Set[str], str | None, str | None]],
        scheduler: AsyncIOScheduler,
        logger: logging.Logger = logging.getLogger(__name__),
    ) -> None:
        super().__init__()

        self._data_provoider = data_provider
        self._notification_queue = notification_queue
        self._sessions: Dict[str, UserSession] = {}
        self._logger = logger
        self._scheduler = scheduler

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
