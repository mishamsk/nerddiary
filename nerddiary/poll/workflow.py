import csv
import datetime
import enum
from copy import deepcopy
from io import StringIO
from uuid import uuid4

from ..primitive.valuelabel import ValueLabel
from ..user.user import User
from .poll import Poll, Question

from typing import Dict, List


class AddAnswerResult(enum.Enum):
    ADDED = enum.auto()
    COMPLETED = enum.auto()
    DELAY = enum.auto()
    ERROR = enum.auto()


class PollWorkflow:
    def __init__(self, poll: Poll, user: User) -> None:
        assert isinstance(poll, Poll)

        self._poll_run_id = uuid4()

        # deepcopy poll to prevent config reloads impacting ongoing polls
        self._poll = deepcopy(poll)
        self._answers_raw: Dict[int, ValueLabel] = {}
        self._user = user
        self._current_question_index: int = 0

        user_timezone = user.timezone
        if self._poll.hours_over_midgnight:
            now = datetime.datetime.now(user_timezone)
            check = now - datetime.timedelta(hours=self._poll.hours_over_midgnight)
            if check.date() < now.date():
                self._poll_start_timestamp = check
            else:
                self._poll_start_timestamp = datetime.datetime.now(user_timezone)
        else:
            self._poll_start_timestamp = datetime.datetime.now(user_timezone)

        self._delayed_at: datetime.datetime | None = None

    @property
    def poll_run_id(self) -> str:
        return str(self._poll_run_id)

    @property
    def completed(self) -> bool:
        return self._current_question_index == len(self._poll.questions)

    @property
    def current_question(self) -> Question:
        return self._poll.questions[self._current_question_index]

    @property
    def delayed(self) -> bool:
        return self._delayed_at is not None

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

        if question.delay_on and question._type.get_serializable_value(value) in question.delay_on:
            self._delayed_at = datetime.datetime.now()
            return AddAnswerResult.DELAY

        self._add_answer(value, self._current_question_index)
        if self._next_question():
            return AddAnswerResult.ADDED
        else:
            return AddAnswerResult.COMPLETED

    def get_select_raw(self) -> List[ValueLabel] | None:

        cur_question = self._poll.questions[self._current_question_index]

        depends_on = cur_question.depends_on

        ret = None
        if depends_on:
            dep_value = self._answers_raw[self._poll._questions_dict[depends_on]._order]

            ret = cur_question._type.get_answer_options(dep_value=dep_value, user=self._user)
        else:
            ret = cur_question._type.get_answer_options(user=self._user)

        return ret

    def get_select_serialized(self) -> Dict[str, str] | None:
        raw = self.get_select_raw()

        if not raw:
            return None

        ret = {}
        question = self._poll.questions[self._current_question_index]

        for sel_val in raw:
            ret[question._type.get_serializable_value(sel_val.value)] = sel_val.label

        return ret

    def get_save_data(self) -> str:

        ret = []
        ret.append(self._poll_start_timestamp)

        for q_index, value in self._answers_raw.items():
            question = self._poll.questions[q_index]

            if question.ephemeral:
                continue

            ret.append(question._type.get_serializable_value(value))

        csv_str = StringIO()
        writer = csv.writer(csv_str, dialect="excel", quoting=csv.QUOTE_ALL)
        writer.writerow(ret)

        return csv_str.getvalue()
