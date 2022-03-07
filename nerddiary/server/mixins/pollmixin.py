from __future__ import annotations

import json

from jsonrpcserver import Error, Result, Success, method

from ..proto import ServerProtocol
from ..rpc import RPCErrors
from ..schema import PollBaseSchema, PollsSchema
from ..session.status import UserSessionStatus


class PollMixin:
    @method  # type:ignore
    async def get_polls(self: ServerProtocol, user_id: str) -> Result:
        self._logger.debug("Processing RPC call")

        ses = await self._sessions.get(user_id)

        if not ses:
            return Error(RPCErrors.ERROR_GETTING_SESSION, "Internal error. Failed to retrieve session")

        if not ses.user_status >= UserSessionStatus.CONFIGURED:
            return Error(RPCErrors.SESSION_INCORRECT_STATUS, "User has no configuration yet")

        polls = []
        if ses._user_config.polls:
            for poll in ses._user_config.polls:
                polls.append(
                    PollBaseSchema(poll_name=poll.poll_name, command=poll.command, description=poll.description).json(
                        exclude_unset=True
                    )
                )

        ret = {
            "schema": "PollsSchema",
            "data": PollsSchema(polls=polls).dict(exclude_unset=True),
        }
        return Success(json.dumps(ret))

    @method  # type:ignore
    async def start_poll(self: ServerProtocol, user_id: str, poll_name: str) -> Result:
        self._logger.debug("Processing RPC call")

        ses = await self._sessions.get(user_id)

        if not ses:
            return Error(RPCErrors.ERROR_GETTING_SESSION, "Internal error. Failed to retrieve session")

        if not ses.user_status >= UserSessionStatus.CONFIGURED:
            return Error(RPCErrors.SESSION_INCORRECT_STATUS, "User has no configuration yet")
        assert ses._user_config

        poll = ses._user_config._polls_dict.get(poll_name)
        if poll is None:
            return Error(RPCErrors.ERROR_POLL_NOT_FOUND, f"Poll with {poll_name=} wasn't found")

        # session function...
        # workflow = PollWorkflow(poll=poll, user=ses._user_config)

        ret = {
            "schema": "PollsSchema",
            "data": PollsSchema(polls=[]).dict(exclude_unset=True),
        }
        return Success(json.dumps(ret))
