from __future__ import annotations

from nerddiary.server.session.status import UserSessionStatus

from jsonrpcserver import Error, Result, Success, method

from ..proto import ServerProtocol
from ..rpc import RPCErrors
from ..schema import PollBaseSchema


class PollMixin:
    @method  # type:ignore
    async def get_polls(self: ServerProtocol, user_id: str) -> Result:
        self._logger.debug("Processing RPC call")

        ses = await self._sessions.get(user_id)

        if not ses:
            return Error(RPCErrors.ERROR_GETTING_SESSION, "Internal error. Failed to retrieve session")

        if not ses.user_status >= UserSessionStatus.CONFIGURED:
            return Error(RPCErrors.SESSION_INCORRECT_STATUS, "User has no configuration yet")

        ret = []
        if ses._user_config.polls:
            for poll in ses._user_config.polls:
                ret.append(
                    PollBaseSchema(poll_name=poll.poll_name, command=poll.command, description=poll.description).json(
                        exclude_unset=True
                    )
                )

            return Success("[" + ",".join(ret) + "]")
        else:
            return Success("[]")
