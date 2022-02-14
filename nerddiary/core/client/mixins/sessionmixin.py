from __future__ import annotations

from pydantic import ValidationError

from ...server.schema import UserSessionSchema
from ..proto import ClientProtocol
from ..rpc import RPCError


class SessionMixin:
    async def get_session(self: ClientProtocol, user_id: str) -> UserSessionSchema | None:
        local_ses = self._sessions.get(user_id)

        if not local_ses:
            try:
                res = await self._run_rpc("get_session", params={"user_id": str(user_id)})
                local_ses = UserSessionSchema.parse_raw(res)
                self._sessions[user_id] = local_ses
            except ValidationError:
                self._logger.error("Received incorrect session data from the server")
            except RPCError:
                pass

        return local_ses

    async def unlock_session(self: ClientProtocol, session: UserSessionSchema, password: str) -> bool:
        try:
            res = await self._run_rpc("unlock_session", params={"user_id": session.user_id, "password": password})
        except RPCError:
            return False

        return res
