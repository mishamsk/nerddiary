from __future__ import annotations

from jsonrpcserver import Error, Result, Success, method

from ...error.error import NerdDiaryError
from ..proto import ServerProtocol
from ..schema import PollExtendedSchema, PollsSchema


class PollMixin:
    @method  # type:ignore
    async def get_polls(self: ServerProtocol, user_id: str) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        polls = None
        try:
            polls = await ses.get_polls()
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        polls_ret = []
        if polls:
            for poll in polls:
                polls_ret.append(
                    PollExtendedSchema(
                        user_id=user_id, poll_name=poll.poll_name, command=poll.command, description=poll.description
                    )
                )

        ret = {
            "schema": "PollsSchema",
            "data": PollsSchema(polls=polls_ret).dict(exclude_unset=True),
        }
        self._logger.debug("Success")
        return Success(ret)

    @method  # type:ignore
    async def start_poll(self: ServerProtocol, user_id: str, poll_name: str) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        poll_workflow = None
        try:
            poll_workflow = await ses.start_poll(poll_name)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        ret = {
            "schema": "PollWorkflowStateSchema",
            "data": poll_workflow.to_schema().dict(exclude_unset=True),
        }
        self._logger.debug("Success")
        return Success(ret)

    @method  # type:ignore
    async def add_poll_answer(self: ServerProtocol, user_id: str, poll_run_id: str, answer: str) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        poll_workflow = None
        try:
            poll_workflow = await ses.add_poll_answer(poll_run_id=poll_run_id, answer=answer)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        ret = {
            "schema": "PollWorkflowStateSchema",
            "data": poll_workflow.to_schema().dict(exclude_unset=True),
        }
        self._logger.debug("Success")
        return Success(ret)

    @method  # type:ignore
    async def close_poll(self: ServerProtocol, user_id: str, poll_run_id: str, save: bool) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        try:
            if poll_run_id == "*":
                await ses.close_all_polls(save=save)
            else:
                await ses.close_poll(poll_run_id=poll_run_id, save=save)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        self._logger.debug("Success")
        return Success(True)

    @method  # type:ignore
    async def restart_poll(self: ServerProtocol, user_id: str, poll_run_id: str) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        try:
            await ses.restart_poll(poll_run_id=poll_run_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        self._logger.debug("Success")
        return Success(True)

    @method  # type:ignore
    async def get_all_poll_data(self: ServerProtocol, user_id: str) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        try:
            data = await ses.get_all_poll_data()
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        ret = {
            "schema": "PollLogsSchema",
            "data": {"logs": data},
        }
        self._logger.debug("Success")
        return Success(ret)
