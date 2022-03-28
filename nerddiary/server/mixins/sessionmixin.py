from __future__ import annotations

from jsonrpcserver import Error, InvalidParams, Result, Success, method

from ...error.error import NerdDiaryError
from ..proto import ServerProtocol
from ..schema import UserSessionSchema


class SessionMixin:
    @method  # type:ignore
    async def get_session(self: ServerProtocol, user_id: str) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        ret = {
            "schema": "UserSessionSchema",
            "data": UserSessionSchema(user_id=ses.user_id, user_status=ses.user_status).dict(exclude_unset=True),
        }
        self._logger.debug("Success")
        return Success(ret)

    @method  # type:ignore
    async def unlock_session(
        self: ServerProtocol, user_id: str, password: str | None = None, key: str | None = None
    ) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        bkey = None
        if key:
            bkey = key.encode()

        pass_or_key = bkey or password
        if not pass_or_key:
            return InvalidParams("Password or key must be present")

        try:
            await ses.unlock(pass_or_key)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        self._logger.debug("Success")
        return Success(True)

    @method  # type:ignore
    async def set_config(self: ServerProtocol, user_id: str, config: str) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            return Error(err.code, err.message, err.data)

        try:
            await ses.set_config(config=config)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        self._logger.debug("Success")
        return Success(True)
