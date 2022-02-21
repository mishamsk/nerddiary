""" String session """

from __future__ import annotations

import logging

from pydantic import BaseModel, DirectoryPath, Protocol, ValidationError

from .session import SessionCorruptionError, SessionCorruptionType, SessionSpawner, UserSession, UserSessionStatus

from typing import TYPE_CHECKING, Any, Dict, Set, Tuple

if TYPE_CHECKING:
    import asyncio

    from ...data.data import DataProvider
    from ..schema import NotificationType, Schema


class StringSessionSpawnerParams(BaseModel):
    base_path: DirectoryPath


class StringSessionSpawner(SessionSpawner):
    def __init__(
        self,
        params: Dict[str, Any] | None,
        data_provider: DataProvider,
        notification_queue: asyncio.Queue[Tuple[NotificationType, Schema | None, Set[str], str | None, str | None]],
        logger: logging.Logger = logging.getLogger(__name__),
    ) -> None:
        super().__init__(
            params=params, data_provider=data_provider, notification_queue=notification_queue, logger=logger
        )

        self._params = StringSessionSpawnerParams.parse_obj(params)

    async def _load_or_create_session(self, user_id: str) -> UserSession:
        self._logger.debug("Loading session")
        self._params.base_path.joinpath(user_id).mkdir(parents=True, exist_ok=True)
        session_file_path = self._params.base_path.joinpath(user_id, "session")
        session_exists = session_file_path.exists()
        lock_exists = self._data_provoider.check_lock_exist(user_id)
        if session_exists and not lock_exists:
            raise SessionCorruptionError(SessionCorruptionType.SESSION_NO_LOCK)

        session = None

        try:
            if not session_exists:
                self._logger.debug("Session didn't exist. Creating")
                session = UserSession(user_id=user_id, user_status=UserSessionStatus.NEW)
            else:
                self._logger.debug("Session exists. Loading")
                session = UserSession.parse_file(
                    session_file_path, content_type="application/json", proto=Protocol.json
                )
                session.user_status = UserSessionStatus.LOCKED
            pass
        except ValidationError:
            raise SessionCorruptionError(SessionCorruptionType.DATA_PARSE_ERROR)

        session._session_spawner = self
        return session

    async def _close_session(self, user_id: str):
        self._logger.debug("Closing session")
        session = self._sessions[user_id]
        self._params.base_path.joinpath(session.user_id).mkdir(parents=True, exist_ok=True)
        session_file_path = self._params.base_path.joinpath(session.user_id, "session")

        if session._data_connection:
            if session._user_config:
                session._data_connection.store_config(session._user_config.json(exclude_unset=True, ensure_ascii=False))

        session_file_path.write_bytes(session.json(exclude_unset=True).encode())

    async def _load_sessions(self) -> Dict[str, UserSession]:
        sessions = {}

        for file in self._params.base_path.iterdir():
            if file.is_dir():
                try:
                    user_id = str(file.name)
                    sessions[user_id] = await self._load_or_create_session(user_id)
                except SessionCorruptionError as e:
                    self._logger.warning(f"Failed to load session, skipping. Reason: {str(e)}")

        return sessions
