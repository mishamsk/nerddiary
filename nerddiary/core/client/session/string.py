""" String session """

from __future__ import annotations

from pydantic import BaseModel, DirectoryPath

from ...data.data import DataProvider
from .session import SessionCorruptionError, SessionCorruptionType, SessionSpawner, UserSession, UserSessionStatus

from typing import Any, Dict


class StringSessionSpawnerParams(BaseModel):
    base_path: DirectoryPath


class StringSessionSpawner(SessionSpawner):
    def __init__(self, name: str, params: Dict[str, Any] | None, data_provider: DataProvider) -> None:
        super().__init__(name, params, data_provider)

        self._params = StringSessionSpawnerParams.parse_obj(params)

    async def create_session(self, user_id: str) -> UserSession:
        session_file_path = self._params.base_path.joinpath(self._name, user_id, "session")
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
        self._params.base_path.joinpath(self._name, session.user_id).mkdir(parents=True, exist_ok=True)
        session_file_path = self._params.base_path.joinpath(self._name, session.user_id, "session")

        session_file_path.write_bytes(session.json(exclude_unset=True).encode())
