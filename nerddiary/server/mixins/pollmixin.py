from __future__ import annotations

from jsonrpcserver import Error, Result, Success, method

from ...error.error import NerdDiaryError
from ..proto import ServerProtocol
from ..schema import PollBaseSchema, PollsSchema, PollWorkflowStateSchema


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
                    PollBaseSchema(poll_name=poll.poll_name, command=poll.command, description=poll.description)
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
            "data": PollWorkflowStateSchema(
                poll_run_id=poll_workflow.poll_run_id,
                completed=poll_workflow.completed,
                delayed=poll_workflow.delayed,
                delayed_for=poll_workflow.delayed_for,
                current_question=poll_workflow.current_question.display_name,
                current_question_index=poll_workflow.current_question_index,
                current_question_description=poll_workflow.current_question.description,
                current_question_value_hint=poll_workflow.current_question._type.value_hint,
                current_question_allow_manual_answer=poll_workflow.current_question._type.allows_manual,
                current_question_select_list=poll_workflow.current_question_select_list,
                questions=[q.display_name for q in poll_workflow.questions if q.ephemeral is False],
                answers=[a.label for a in poll_workflow.answers],
            ).dict(exclude_unset=True),
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

        # TODO: Maybe some delay processing and such
        poll_workflow = None
        try:
            poll_workflow = await ses.add_poll_answer(poll_run_id=poll_run_id, answer=answer)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        ret = {
            "schema": "PollWorkflowStateSchema",
            "data": PollWorkflowStateSchema(
                poll_run_id=poll_workflow.poll_run_id,
                completed=poll_workflow.completed,
                delayed=poll_workflow.delayed,
                delayed_for=poll_workflow.delayed_for,
                current_question=poll_workflow.current_question.display_name,
                current_question_index=poll_workflow.current_question_index,
                current_question_description=poll_workflow.current_question.description,
                current_question_value_hint=poll_workflow.current_question._type.value_hint,
                current_question_allow_manual_answer=poll_workflow.current_question._type.allows_manual,
                current_question_select_list=poll_workflow.current_question_select_list,
                questions=[q.display_name for q in poll_workflow.questions if q.ephemeral is False],
                answers=[a.label for a in poll_workflow.answers],
            ).dict(exclude_unset=True),
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
            await ses.close_poll(poll_run_id=poll_run_id, save=save)
        except NerdDiaryError as err:
            self._logger.debug(f"Error: {err!r}")
            return Error(err.code, err.message, err.data)

        self._logger.debug("Success")
        return Success(True)
