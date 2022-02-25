from __future__ import annotations

import json

from nerddiary.server.session.status import UserSessionStatus

from jsonrpcserver import Error, InvalidParams, Result, Success, method

from ..proto import ServerProtocol
from ..rpc import RPCErrors
from ..schema import UserSessionSchema


class SessionMixin:
    @method  # type:ignore
    async def get_session(self: ServerProtocol, user_id: str) -> Result:
        self._logger.debug("Processing RPC call")

        ses = await self._sessions.get(user_id)

        if not ses:
            return Error(RPCErrors.ERROR_GETTING_SESSION, "Internal error. Failed to retrieve session")

        ret = {
            "schema": "UserSessionSchema",
            "data": UserSessionSchema(user_id=ses.user_id, user_status=ses.user_status).dict(exclude_unset=True),
        }
        return Success(json.dumps(ret))

    @method  # type:ignore
    async def unlock_session(
        self: ServerProtocol, user_id: str, password: str | None = None, key: str | None = None
    ) -> Result:
        self._logger.debug("Processing RPC call")

        ses = await self._sessions.get(user_id)

        if not ses:
            return Error(RPCErrors.SESSION_NOT_FOUND, "Session doesn't exist")

        bkey = None
        if key:
            bkey = key.encode()

        pass_or_key = bkey or password
        if not pass_or_key:
            return InvalidParams("Password or key must be present")

        if not await ses.unlock(pass_or_key):
            return Error(RPCErrors.SESSION_INCORRECT_PASSWORD_OR_KEY, "Incorrect password or key")

        return Success(True)

    @method  # type:ignore
    async def set_config(self: ServerProtocol, user_id: str, config: str) -> Result:
        self._logger.debug("Processing RPC call")

        ses = await self._sessions.get(user_id)

        if not ses:
            return Error(RPCErrors.SESSION_NOT_FOUND, "Session doesn't exist")

        if not ses.user_status > UserSessionStatus.LOCKED:
            return Error(RPCErrors.SESSION_INCORRECT_STATUS, "Session is locked")

        if await ses.set_config(config=config):
            return Success(True)
        else:
            return InvalidParams("Configuration is not valid")
