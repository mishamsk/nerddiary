from __future__ import annotations

import datetime
import enum
import json
from copy import deepcopy
from uuid import UUID, uuid4

from nerddiary.server.schema import PollWorkflowStateSchema

from pydantic import ValidationError

from ..error.error import NerdDiaryError, NerdDiaryErrorCode
from ..primitive.valuelabel import ValueLabel
from ..user.user import User
from .poll import Poll, Question

from typing import Any, Dict, List, Tuple


class AddAnswerResult(enum.Enum):
    ADDED = enum.auto()
    COMPLETED = enum.auto()
    DELAY = enum.auto()
    ERROR = enum.auto()


class PollWorkflow:
    def __init__(
        self,
        poll: Poll,
        user: User,
        poll_run_id: UUID | str | int | bytes | None = None,
        log_id: int | None = None,
        answers_raw: Dict[str, ValueLabel] | None = None,
        current_question_code: str | None = None,
        poll_ts: datetime.datetime | None = None,
        delayed_at: datetime.datetime | None = None,
    ) -> None:

        if poll_run_id is None:
            poll_run_id = uuid4()

        if not isinstance(poll_run_id, UUID):
            if isinstance(poll_run_id, int):
                poll_run_id = UUID(int=poll_run_id)
            if isinstance(poll_run_id, str):
                poll_run_id = UUID(poll_run_id)
            if isinstance(poll_run_id, bytes):
                poll_run_id = UUID(bytes=poll_run_id)

        self._poll_run_id = poll_run_id
        self._log_id: int | None = log_id

        # deepcopy poll to prevent config reloads impacting ongoing polls
        self._poll = deepcopy(poll)
        self._answers_raw: Dict[str, ValueLabel] = answers_raw if answers_raw else {}
        self._user = user
        self._current_question_code: str = current_question_code or self._poll.questions[0].code

        if poll_ts is None:
            user_timezone = user.timezone
            now = datetime.datetime.now(user_timezone)
            if self._poll.hours_over_midgnight:
                check = now - datetime.timedelta(hours=self._poll.hours_over_midgnight)
                if check.date() < now.date():
                    self._poll_ts = check.replace(hour=23, minute=59, second=59)
                else:
                    self._poll_ts = now
            else:
                self._poll_ts = now
        else:
            self._poll_ts = poll_ts

        self._delayed_at: datetime.datetime | None = delayed_at

    @property
    def poll_run_id(self) -> UUID:
        return self._poll_run_id

    @property
    def poll_name(self) -> str:
        return self._poll.poll_name

    @property
    def poll_ts(self) -> datetime.datetime:
        return self._poll_ts

    @property
    def log_id(self) -> int | None:
        return self._log_id

    @log_id.setter
    def log_id(self, value: int):
        self._log_id = value

    @property
    def completed(self) -> bool:
        return self._current_question_code == self._poll.questions[-1].code

    @property
    def delayed(self) -> bool:
        return self.delayed_until is not None

    @property
    def delayed_until(self) -> datetime.datetime | None:
        if self._delayed_at is not None:
            assert self.current_delay_time
            return self._delayed_at + self.current_delay_time

        return None

    @property
    def delayed_for(self) -> datetime.timedelta | None:
        return self.current_question.delay_time if self.delayed else None

    @property
    def current_question(self) -> Question:
        return self._poll._questions_dict[self._current_question_code]

    @property
    def current_question_code(self) -> str:
        return self._current_question_code

    @property
    def current_question_select_list(self) -> List[ValueLabel] | None:
        question = self._poll._questions_dict[self._current_question_code]

        depends_on = question.depends_on

        if depends_on:
            dep_value = self._answers_raw[self._poll._questions_dict[depends_on].code]
            return question._type.get_answer_options(dep_value=dep_value, user=self._user)
        else:
            return question._type.get_answer_options(user=self._user)

    @property
    def questions(self) -> List[Question]:
        return self._poll.questions

    @property
    def answers(self) -> List[ValueLabel]:
        return [val for q_code, val in self._answers_raw.items() if not self._poll._questions_dict[q_code].ephemeral]

    @property
    def current_delay_time(self) -> datetime.timedelta | None:
        return self._poll._questions_dict[self._current_question_code].delay_time

    def _add_answer(self, val: ValueLabel, question_code: str):
        self._answers_raw[question_code] = val

    def _next_question(self) -> bool:
        if self.completed:
            return False

        self._current_question_code = self._get_next_question(self._current_question_code).code
        new_question = self._poll._questions_dict[self._current_question_code]

        if new_question._type.is_auto:
            # If auto question - store value and recursively proceed to the next
            self._process_auto_question()
            return self._next_question()

        return True

    def _get_next_question(self, current_question_code: str) -> Question:
        return self._poll.questions[self._poll._questions_dict[current_question_code]._order + 1]

    def _process_auto_question(self) -> None:
        question = self._poll._questions_dict[self._current_question_code]

        depends_on = question.depends_on

        if depends_on:
            dep_value = self._answers_raw[self._poll._questions_dict[depends_on].code]
            value = question._type.get_auto_value(dep_value=dep_value, user=self._user)
        else:
            value = question._type.get_auto_value(user=self._user)

        assert value is not None

        self._add_answer(value, self._current_question_code)

    def add_answer(self, answer: str) -> AddAnswerResult:

        if self.delayed_until is not None:
            if datetime.datetime.now() < self.delayed_until:
                return AddAnswerResult.DELAY
            else:
                self._delayed_at = None

        question = self._poll._questions_dict[self._current_question_code]
        value = None
        depends_on = question.depends_on

        if depends_on:
            dep_value = self._answers_raw[self._poll._questions_dict[depends_on].code]
            value = question._type.get_value_from_answer(answer=answer, dep_value=dep_value, user=self._user)
        else:
            value = question._type.get_value_from_answer(answer=answer, user=self._user)

        if not value:
            return AddAnswerResult.ERROR

        if question.delay_on and question._type.serialize_value(value) in question.delay_on:
            self._delayed_at = datetime.datetime.now()
            return AddAnswerResult.DELAY

        if question.skip_on:
            ser_value = question._type.serialize_value(value)
            if ser_value in question.skip_on:
                skip_to_code = question.skip_on[ser_value]

                while True:
                    self._add_answer(value, self._current_question_code)
                    if self._next_question():
                        question = self._poll._questions_dict[self._current_question_code]

                        if question.code == skip_to_code:
                            return AddAnswerResult.ADDED

                        depends_on = question.depends_on
                        assert question.default_value  # should never happen because of config validation
                        if depends_on:
                            dep_value = self._answers_raw[self._poll._questions_dict[depends_on].code]
                            value = question._type.deserialize_value(
                                serialized=question.default_value, dep_value=dep_value, user=self._user
                            )
                        else:
                            value = question._type.deserialize_value(serialized=question.default_value)
                    else:
                        return AddAnswerResult.COMPLETED

        self._add_answer(value, self._current_question_code)
        if self._next_question():
            return AddAnswerResult.ADDED
        else:
            return AddAnswerResult.COMPLETED

    def add_default(self) -> AddAnswerResult:
        if self.delayed_until is not None:
            if datetime.datetime.now() < self.delayed_until:
                return AddAnswerResult.DELAY
            else:
                self._delayed_at = None

        question = self._poll._questions_dict[self._current_question_code]
        value = None
        depends_on = question.depends_on

        if question.default_value is None:
            return AddAnswerResult.ERROR

        if depends_on:
            dep_value = self._answers_raw[self._poll._questions_dict[depends_on].code]
            value = question._type.deserialize_value(
                serialized=question.default_value, dep_value=dep_value, user=self._user
            )
        else:
            value = question._type.deserialize_value(serialized=question.default_value)

        self._add_answer(value, self._current_question_code)
        if self._next_question():
            return AddAnswerResult.ADDED
        else:
            return AddAnswerResult.COMPLETED

    def get_save_data(self) -> Tuple[datetime.datetime, str]:

        ret = {}

        for q_code, question in self._poll._questions_dict.items():
            if question.ephemeral:
                continue

            if q_code in self._answers_raw:
                value = question._type.serialize_value(self._answers_raw[q_code])

                ret[q_code] = value

        return (self._poll_ts, json.dumps(ret))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "poll": self._poll.dict(exclude_unset=True),
            "user": self._user.dict(exclude_unset=True),
            "poll_run_id": str(self._poll_run_id),
            "log_id": self._log_id,
            "answers_raw": {q_code: answer.dict() for q_code, answer in self._answers_raw.items()},
            "current_question_code": self._current_question_code,
            "poll_ts": self._poll_ts.isoformat(),
            "delayed_at": self._delayed_at.isoformat() if self._delayed_at else "",
        }

    def to_schema(self) -> PollWorkflowStateSchema:
        return PollWorkflowStateSchema(
            user_id=self._user.id,
            poll_name=self.poll_name,
            poll_run_id=str(self.poll_run_id),
            poll_ts=self.poll_ts,
            completed=self.completed,
            delayed=self.delayed,
            delayed_for=str(self.delayed_for) if self.delayed_for else "",
            current_question_display_name=self.current_question.display_name,
            current_question_code=self.current_question_code,
            current_question_description=self.current_question.description,
            current_question_value_hint=self.current_question._type.value_hint,
            current_question_allow_manual_answer=self.current_question._type.allows_manual,
            current_question_select_list=self.current_question_select_list,
            current_question_default_value=self.current_question.default_value,
            questions=[q.display_name for q in self.questions if q.ephemeral is False],
            answers=[a.label for a in self.answers],
        )

    @classmethod
    def from_store_data(
        cls, poll: Poll, user: User, poll_ts: datetime.datetime, log: str, log_id: int | None = None
    ) -> PollWorkflow:
        answers_raw: Dict[str, ValueLabel] = {}

        if log:
            row = json.loads(log)
            for q_code, question in poll._questions_dict.items():
                if question.ephemeral:
                    # Ephemeral question values are not stored, so we just skipping them. Should not be a problem
                    continue

                if q_code not in row:
                    continue

                depends_on = question.depends_on

                if depends_on:
                    dep_value = answers_raw[poll._questions_dict[depends_on].code]
                    answers_raw[q_code] = question._type.deserialize_value(
                        serialized=row[q_code], dep_value=dep_value, user=user
                    )
                else:
                    answers_raw[q_code] = question._type.deserialize_value(serialized=row[q_code], user=user)

        return cls(
            poll=poll,
            user=user,
            log_id=log_id,
            answers_raw=answers_raw,
            poll_ts=poll_ts,
        )

    @classmethod
    def from_dict(cls, serialized: Dict[str, Any]) -> PollWorkflow:
        try:
            poll = Poll.parse_obj(serialized["poll"])
            user = User.parse_obj(serialized["user"])
            poll_run_id = UUID(serialized["poll_run_id"])
            log_id = serialized["log_id"]
            answers_raw = {i: ValueLabel.parse_obj(v) for i, v in serialized["answers_raw"]}
            current_question_code = serialized["current_question_code"]
            poll_ts = datetime.datetime.fromisoformat(serialized["poll_ts"])
            delayed_at = (
                datetime.datetime.fromisoformat(serialized["delayed_at"]) if serialized["delayed_at"] != "" else None
            )
        except ValidationError as err:
            raise NerdDiaryError(NerdDiaryErrorCode.WORKFLOW_FAILED_DESERIALIZE, data=err.errors)
        except ValueError as err:
            raise NerdDiaryError(NerdDiaryErrorCode.WORKFLOW_FAILED_DESERIALIZE, data=err.args)

        return cls(
            poll=poll,
            user=user,
            poll_run_id=poll_run_id,
            log_id=log_id,
            answers_raw=answers_raw,
            current_question_code=current_question_code,
            poll_ts=poll_ts,
            delayed_at=delayed_at,
        )
