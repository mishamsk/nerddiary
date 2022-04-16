from __future__ import annotations

import datetime

from jsonrpcserver import Error, InvalidParams, Result, Success, method

from ...error.error import NerdDiaryError
from ..proto import ServerProtocol
from ..schema import PollExtendedSchema, PollLogsSchema, PollsSchema


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
    async def start_poll(self: ServerProtocol, user_id: str, poll_name: str, poll_ts_iso: str | None = None) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        poll_ts = None
        if poll_ts_iso:
            try:
                poll_ts = datetime.datetime.fromisoformat(poll_ts_iso)
            except ValueError:
                self._logger.exception(f"Error parsing poll_ts_iso: {poll_ts_iso!r}")
                return InvalidParams(f"Invalid ISO timestamp: {poll_ts_iso}")

        poll_workflow = None
        try:
            poll_workflow = await ses.start_poll(poll_name, poll_ts=poll_ts)
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
    async def add_default_poll_answer(self: ServerProtocol, user_id: str, poll_run_id: str) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        poll_workflow = None
        try:
            poll_workflow = await ses.add_default_poll_answer(poll_run_id=poll_run_id)
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
            poll_workflow = await ses.restart_poll(poll_run_id=poll_run_id)
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
    async def get_poll_data(
        self: ServerProtocol,
        user_id: str,
        poll_name: str | None = None,
        count: int | None = None,
        skip: int | None = None,
    ) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        try:
            data = await ses.get_poll_data(poll_name=poll_name, count=count, skip=skip)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        ret = {
            "schema": "PollLogsSchema",
            "data": data.dict(),
        }
        self._logger.debug("Success")
        return Success(ret)

    @method  # type:ignore
    async def get_poll_log(
        self: ServerProtocol,
        user_id: str,
        log_id: int,
    ) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        try:
            poll_workflow = await ses.get_poll_workflow_from_log(log_id=log_id)
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
    async def get_poll_worflow(self: ServerProtocol, user_id: str, poll_run_id: str) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        try:
            poll_workflow = await ses.get_poll_worflow(poll_run_id=poll_run_id)
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
    async def log_poll_data(self: ServerProtocol, user_id: str, poll_data: str) -> Result:
        self._logger.debug("Processing RPC call")

        try:
            ses = await self._sessions.get(user_id)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        ret = 0
        try:
            ret = await ses.log_poll_data(data=PollLogsSchema.parse_raw(poll_data))
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        self._logger.debug("Success")
        return Success(ret)
