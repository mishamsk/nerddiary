""" String session """

from __future__ import annotations

import asyncio

from apscheduler.schedulers.base import BaseScheduler
from pydantic import BaseModel, DirectoryPath

from ...data.data import DataProvider
from .session import SessionCorruptionError, SessionCorruptionType, SessionSpawner, UserSession, UserSessionStatus

from typing import Any, Dict


class StringSessionSpawnerParams(BaseModel):
    base_path: DirectoryPath


class StringSessionSpawner(SessionSpawner):
    def __init__(
        self,
        params: Dict[str, Any] | None,
        data_provider: DataProvider,
        scheduler: BaseScheduler,
        job_queue: asyncio.Queue,
    ) -> None:
        super().__init__(params=params, data_provider=data_provider, scheduler=scheduler, job_queue=job_queue)

        self._params = StringSessionSpawnerParams.parse_obj(params)

    async def create_session(self, user_id: str) -> UserSession:
        session_file_path = self._params.base_path.joinpath(user_id, "session")
        session_exists = session_file_path.exists()
        lock_exists = self._data_provoider.check_lock_exist(user_id)
        if session_exists and not lock_exists:
            raise SessionCorruptionError(SessionCorruptionType.SESSION_NO_LOCK)

        session = None

        if not session_exists:
            session = UserSession(user_id=user_id)
        else:
            session = UserSession.parse_file(session_file_path, content_type="json")

        session.user_status = UserSessionStatus.NEW if not lock_exists else UserSessionStatus.LOCKED
        session._session_spawner = self
        return session

    async def close_session(self, session: UserSession):
        self._params.base_path.joinpath(session.user_id).mkdir(parents=True, exist_ok=True)
        session_file_path = self._params.base_path.joinpath(session.user_id, "session")

        session_file_path.write_bytes(session.json(exclude_unset=True).encode())
