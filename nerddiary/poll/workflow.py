from __future__ import annotations

import csv
import datetime
import enum
import itertools
from copy import deepcopy
from io import StringIO
from uuid import UUID, uuid4

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
        poll_run_id: UUID | None = uuid4(),
        log_id: int | None = None,
        answers_raw: Dict[int, ValueLabel] = {},
        current_question_index: int = 0,
        poll_ts: datetime.datetime | None = None,
        delayed_at: datetime.datetime | None = None,
    ) -> None:

        self._poll_run_id = poll_run_id
        self._log_id: int | None = log_id

        # deepcopy poll to prevent config reloads impacting ongoing polls
        self._poll = deepcopy(poll)
        self._answers_raw: Dict[int, ValueLabel] = answers_raw
        self._user = user
        self._current_question_index: int = current_question_index

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
    def poll_run_id(self) -> str:
        return str(self._poll_run_id)

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
        return self._current_question_index == len(self._poll.questions)

    @property
    def delayed(self) -> bool:
        return self._delayed_at is not None

    @property
    def delayed_for(self) -> str:
        return str(self.current_question.delay_time) if self.delayed else ""

    @property
    def current_question(self) -> Question:
        return self._poll.questions[self._current_question_index]

    @property
    def current_question_index(self) -> int:
        return self._current_question_index

    @property
    def current_question_select_list(self) -> List[ValueLabel] | None:
        question = self._poll.questions[self._current_question_index]

        depends_on = question.depends_on

        if depends_on:
            dep_value = self._answers_raw[self._poll._questions_dict[depends_on]._order]
            return question._type.get_answer_options(dep_value=dep_value, user=self._user)
        else:
            return question._type.get_answer_options(user=self._user)

    @property
    def questions(self) -> List[Question]:
        return self._poll.questions

    @property
    def answers(self) -> List[ValueLabel]:
        return [val for q_index, val in self._answers_raw.items() if not self._poll.questions[q_index].ephemeral]

    @property
    def current_delay_time(self) -> datetime.timedelta | None:
        return self._poll.questions[self._current_question_index].delay_time

    def _add_answer(self, val: ValueLabel, question_index: int):
        self._answers_raw[question_index] = val

    def _next_question(self) -> bool:
        if self.completed:
            return False

        self._current_question_index += 1
        new_question = self._poll.questions[self._current_question_index]

        if new_question._type.is_auto:
            # If auto question - store value and recursively proceed to the next
            self._process_auto_question()
            return self._next_question()

        return True

    def _process_auto_question(self) -> None:
        question = self._poll.questions[self._current_question_index]

        depends_on = question.depends_on

        if depends_on:
            dep_value = self._answers_raw[self._poll._questions_dict[depends_on]._order]
            value = question._type.get_auto_value(dep_value=dep_value, user=self._user)
        else:
            value = question._type.get_auto_value(user=self._user)

        assert value is not None

        self._add_answer(value, self._current_question_index)

    def add_answer(self, answer: str) -> AddAnswerResult:

        if self._delayed_at is not None:
            assert self.current_delay_time
            if datetime.datetime.now() - self._delayed_at < self.current_delay_time:
                return AddAnswerResult.DELAY
            else:
                self._delayed_at = None

        question = self._poll.questions[self._current_question_index]
        value = None
        depends_on = question.depends_on

        if depends_on:
            dep_value = self._answers_raw[self._poll._questions_dict[depends_on]._order]
            value = question._type.get_value_from_answer(answer=answer, dep_value=dep_value, user=self._user)
        else:
            value = question._type.get_value_from_answer(answer=answer, user=self._user)

        if not value:
            return AddAnswerResult.ERROR

        if question.delay_on and question._type.serialize_value(value) in question.delay_on:
            self._delayed_at = datetime.datetime.now()
            return AddAnswerResult.DELAY

        self._add_answer(value, self._current_question_index)
        if self._next_question():
            return AddAnswerResult.ADDED
        else:
            return AddAnswerResult.COMPLETED

    def get_save_data(self) -> Tuple[datetime.datetime, str]:

        ret = []
        ret.append(self._poll_ts.isoformat())

        for q_index, question in zip(itertools.count(), self._poll.questions):
            if question.ephemeral:
                continue

            value = ""
            if q_index in self._answers_raw:
                value = question._type.serialize_value(self._answers_raw[q_index])

            ret.append(value)

        csv_str = StringIO()
        writer = csv.writer(csv_str, dialect="excel", quoting=csv.QUOTE_ALL)
        writer.writerow(ret)

        return (self._poll_ts, csv_str.getvalue())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "poll": self._poll.dict(exclude_unset=True),
            "user": self._user.dict(exclude_unset=True),
            "poll_run_id": self._poll_run_id.int,
            "log_id": self._log_id,
            "answers_raw": {i: v.dict() for i, v in self._answers_raw.items()},
            "current_question_index": self._current_question_index,
            "poll_ts": self._poll_ts.isoformat(),
            "delayed_at": self._delayed_at.isoformat() if self._delayed_at else "",
        }

    @classmethod
    def from_store_data(cls, poll: Poll, user: User, log_id: int, poll_ts: datetime.datetime, log: str) -> PollWorkflow:
        answers_raw = {}

        if log:
            row = next(csv.reader([log], dialect="excel", quoting=csv.QUOTE_ALL))
            for q_index, question in zip(itertools.count(), poll.questions):
                if question.ephemeral:
                    # Ephemeral question values are not stored, so we just skipping them. Should not be a problem
                    continue

                if row[q_index] != "":
                    depends_on = question.depends_on

                    if depends_on:
                        dep_value = answers_raw[poll._questions_dict[depends_on]._order]
                        answers_raw[q_index] = question._type.get_value_from_answer(
                            answer=row[q_index], dep_value=dep_value, user=user
                        )
                    else:
                        answers_raw[q_index] = question._type.get_value_from_answer(answer=row[q_index], user=user)

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
            poll_run_id = UUID(int=serialized["poll_run_id"])
            log_id = serialized["log_id"]
            answers_raw = {i: ValueLabel.parse_obj(v) for i, v in serialized["answers_raw"]}
            current_question_index = serialized["current_question_index"]
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
            current_question_index=current_question_index,
            poll_ts=poll_ts,
            delayed_at=delayed_at,
        )
