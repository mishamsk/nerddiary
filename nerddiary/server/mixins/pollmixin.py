from __future__ import annotations

from nerddiary.server.session.session import SessionError, SessionErrorType

from jsonrpcserver import Error, Result, Success, method

from ..proto import ServerProtocol
from ..rpc import RPCErrors
from ..schema import PollBaseSchema, PollsSchema, PollWorkflowStateSchema


class PollMixin:
    @method  # type:ignore
    async def get_polls(self: ServerProtocol, user_id: str) -> Result:
        self._logger.debug("Processing RPC call")

        ses = await self._sessions.get(user_id)

        if not ses:
            return Error(RPCErrors.ERROR_GETTING_SESSION, "Internal error. Failed to retrieve session")

        polls = None
        try:
            polls = await ses.get_polls()
        except SessionError as err:
            if err.type == SessionErrorType.SESSION_INCORRECT_STATUS:
                return Error(RPCErrors.SESSION_INCORRECT_STATUS, "User has no configuration yet")
            else:
                return Error(RPCErrors.ERROR_INTERNAL_ERROR, "Internal error. Failed to retrieve poll list")

        polls_ret = []
        if polls:
            for poll in polls:
                polls_ret.append(
                    PollBaseSchema(poll_name=poll.poll_name, command=poll.command, description=poll.description)
                )

        ret = {
            "schema": "PollsSchema",
            "data": PollsSchema(polls=polls_ret).dict(exclude_unset=True),
        }
        return Success(ret)

    @method  # type:ignore
    async def start_poll(self: ServerProtocol, user_id: str, poll_name: str) -> Result:
        self._logger.debug("Processing RPC call")

        ses = await self._sessions.get(user_id)

        if not ses:
            return Error(RPCErrors.ERROR_GETTING_SESSION, "Internal error. Failed to retrieve session")

        poll_workflow = None
        try:
            poll_workflow = await ses.start_poll(poll_name)
        except SessionError as err:
            match err.type:
                case SessionErrorType.SESSION_INCORRECT_STATUS:
                    return Error(RPCErrors.SESSION_INCORRECT_STATUS, "User has no configuration yet")
                case SessionErrorType.POLL_NOT_FOUND:
                    return Error(RPCErrors.ERROR_POLL_NOT_FOUND, f"Poll with {poll_name=} wasn't found")
                case _:
                    return Error(RPCErrors.ERROR_INTERNAL_ERROR, "Internal error. Failed to retrieve poll list")

        select_list = None
        options = poll_workflow.current_question._type.get_answer_options()
        if options:
            select_list = {vl.value: vl.label for vl in options}

        ret = {
            "schema": "PollWorkflowStateSchema",
            "data": PollWorkflowStateSchema(
                poll_run_id=poll_workflow.poll_run_id,
                completed=poll_workflow.completed,
                delayed=poll_workflow.delayed,
                current_question=poll_workflow.current_question.display_name,
                current_question_index=poll_workflow.current_question_index,
                current_question_description=poll_workflow.current_question.description,
                current_question_value_hint=poll_workflow.current_question._type.value_hint,
                # TODO: switch to type attribute
                current_question_allow_manual_answer=options is None,
                current_question_select_list=select_list,
                questions=[q.display_name for q in poll_workflow.questions if q.ephemeral is False],
                answers=[a.label for a in poll_workflow.answers],
            ).dict(exclude_unset=True),
        }
        return Success(ret)

    @method  # type:ignore
    async def add_poll_answer(self: ServerProtocol, user_id: str, poll_run_id: str, answer: str) -> Result:
        self._logger.debug("Processing RPC call")

        ses = await self._sessions.get(user_id)

        if not ses:
            return Error(RPCErrors.ERROR_GETTING_SESSION, "Internal error. Failed to retrieve session")

        # TODO: Maybe some delay processing and such
        poll_workflow = None
        try:
            poll_workflow = await ses.add_poll_answer(poll_run_id=poll_run_id, answer=answer)
        except SessionError as err:
            match err.type:
                case SessionErrorType.POLL_ANSWER_UNSUPPORTED_VALUE:
                    return Error(RPCErrors.ERROR_POLL_ANSWER_UNSUPPORTED_VALUE, "User has no configuration yet")
                case SessionErrorType.POLL_NOT_FOUND:
                    return Error(RPCErrors.ERROR_POLL_NOT_FOUND, f"Poll with {poll_run_id=} wasn't found")
                case _:
                    return Error(RPCErrors.ERROR_INTERNAL_ERROR, "Internal error. Failed to retrieve poll list")

        select_list = None
        options = poll_workflow.current_question._type.get_answer_options()
        if options:
            select_list = {vl.value: vl.label for vl in options}

        ret = {
            "schema": "PollWorkflowStateSchema",
            "data": PollWorkflowStateSchema(
                poll_run_id=poll_workflow.poll_run_id,
                completed=poll_workflow.completed,
                delayed=poll_workflow.delayed,
                current_question=poll_workflow.current_question.display_name,
                current_question_index=poll_workflow.current_question_index,
                current_question_description=poll_workflow.current_question.description,
                current_question_value_hint=poll_workflow.current_question._type.value_hint,
                # TODO: switch to type attribute
                current_question_allow_manual_answer=options is None,
                current_question_select_list=select_list,
                questions=[q.display_name for q in poll_workflow.questions if q.ephemeral is False],
                answers=[a.label for a in poll_workflow.answers],
            ).dict(exclude_unset=True),
        }
        return Success(ret)
