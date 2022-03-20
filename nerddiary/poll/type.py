""" Poll models for question types """

from __future__ import annotations

import abc
import datetime
import logging
import re

from pydantic import BaseModel, conlist, validator
from pydantic.fields import Field, PrivateAttr

from ..primitive.valuelabel import ValueLabel

import typing as t

if t.TYPE_CHECKING:  # pragma: no cover
    from nerddiary.user.user import User

logger = logging.getLogger(__name__)


class UnsupportedAnswerError(Exception):
    pass


class QuestionType(BaseModel, abc.ABC):
    type: t.ClassVar[str | None] = None

    value_hint: t.Optional[str] = Field(description="Optional text explaining expected answer value format")

    _must_depend: bool = PrivateAttr(False)
    """ True if this type requires a dependent value """

    _auto: bool = PrivateAttr(False)
    """Whether this question is actually a value that is populating without input"""

    @classmethod
    @property
    def supported_types(cls) -> t.Dict[str, t.Type[QuestionType]]:
        def all_subclasses(cls) -> t.Dict[str, t.Type[QuestionType]]:
            subc = {} | {cl.type: cl for cl in cls.__subclasses__() if cl.type is not None}

            sub_subc = {}
            for c in subc.values():
                sub_subc |= all_subclasses(c)

            return subc | sub_subc

        return all_subclasses(cls)

    @property
    def is_auto(self) -> bool:
        """Returns True if type instance autogenerates value"""
        return self._auto

    @property
    def is_dependent(self) -> bool:
        """Returns True if question type's possible values are dependent on another value"""
        return self._must_depend

    @property
    def allows_manual(self) -> bool:
        """Returns True if question type allows arbitrary manual value as input"""
        return not self._must_depend and self.get_answer_options() is None

    def __init__(self, **data):
        super().__init__(**data)

    @abc.abstractmethod
    def get_possible_values(self) -> t.Type[t.Any] | t.List[ValueLabel]:
        pass  # pragma: no cover

    def get_value_from_answer(
        self, answer: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel | None:
        """Raises UnsupportedAnswerError() if string answer value is not supported"""
        if self.is_auto:
            raise NotImplementedError("This type doesn't support user input")

    def get_auto_value(self, dep_value: ValueLabel | None = None, user: User | None = None) -> ValueLabel | None:
        if not self.is_auto:
            raise NotImplementedError("This type doesn't auto generate a value")

    @abc.abstractmethod
    def serialize_value(self, value: ValueLabel) -> str:
        pass  # pragma: no cover

    @abc.abstractmethod
    def deserialize_value(self, serialized: str) -> ValueLabel:
        pass

    def get_answer_options(
        self, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> t.List[ValueLabel[str]] | None:
        if self.is_auto:
            raise NotImplementedError("This type doesn't support user input")

    def check_dependency_type(self, dependency_type: QuestionType) -> bool:
        """Check that this type is compatible with the type of dependency question. Returns `False` for types that may not depend on others"""
        return self._must_depend


class SelectType(QuestionType):

    select: t.List[ValueLabel[str]] = Field(description="List of answer options", min_items=1)  # type:ignore

    def __init__(self, **data):
        super().__init__(**data)

        self._auto = False
        self._must_depend = False

    def get_possible_values(self) -> t.List[ValueLabel]:
        return self.select

    def get_value_from_answer(
        self, answer: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel | None:
        candidates = [vl for vl in self.select if vl.value == answer]
        if not candidates:
            raise UnsupportedAnswerError()

        return candidates[0]

    def serialize_value(self, value: ValueLabel) -> str:
        return str(value.value)

    def deserialize_value(self, serialized: str) -> ValueLabel[str]:
        return ValueLabel[str](value=serialized, label=serialized)

    def get_answer_options(
        self, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> t.List[ValueLabel[str]] | None:
        return self.select


class DependantSelectType(QuestionType):

    select: t.Dict[str, conlist(ValueLabel[str], min_items=1)]  # type:ignore

    def __init__(self, **data):
        super().__init__(**data)

        self._auto = False
        self._must_depend = True

    @validator("select")
    def at_least_one_select_must_exist(cls, v: t.Dict[str, t.Any]):
        if len(v) == 0:
            raise ValueError("Select must not be empty")
        return v

    def get_possible_values(self) -> t.List[ValueLabel]:
        ret = []
        for value_list in self.select.values():
            ret += value_list

        return ret

    def get_value_from_answer(
        self, answer: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel | None:
        if not dep_value:
            raise AttributeError(
                "<get_value_from_answer> called without a dependent value for a question with dependent select list"
            )
        if not isinstance(dep_value.value, str):
            raise AttributeError(
                f"<get_value_from_answer> called with incorrect dependency value. Got {dep_value.value}, expected a string"
            )
        if dep_value.value not in self.select:
            raise AttributeError(
                f"<get_value_from_answer> called with incorrect dependency value. Got {dep_value}, but it doesn't exist among this type's select"
            )

        candidates = [vl for vl in self.select[dep_value.value] if vl.value == answer]
        if not candidates:
            raise UnsupportedAnswerError()

        return candidates[0]

    def serialize_value(self, value: ValueLabel) -> str:
        return str(value.value)

    def deserialize_value(self, serialized: str) -> ValueLabel[str]:
        return ValueLabel[str](value=serialized, label=serialized)

    def get_answer_options(
        self, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> t.List[ValueLabel[str]] | None:
        if not dep_value:
            raise AttributeError(
                "<get_answer_options> called without a dependent value for a question with dependent select list"
            )
        if not isinstance(dep_value.value, str):
            raise AttributeError(
                f"<get_answer_options> called with incorrect value. Got {dep_value.value}, expected a string"
            )

        if dep_value.value not in self.select:
            raise AttributeError(
                f"<get_value_from_answer> called with incorrect dependency value. Got {dep_value}, but it doesn't exist among this type's select"
            )

        return self.select[dep_value.value]

    def check_dependency_type(self, dependency_type: QuestionType) -> bool:
        """Check that this type is compatible with the type of dependency question. Returns `False` for types that may not depend on others"""

        possible_dependency_values = dependency_type.get_possible_values()

        if not isinstance(possible_dependency_values, list):
            return False

        for possible_value in possible_dependency_values:
            if not isinstance(possible_value.value, str) or possible_value.value not in self.select:
                return False

        return True


class TimestampType(QuestionType):
    type = "timestamp"

    def __init__(self, **data):
        super().__init__(**data)

        self._auto = True
        self._must_depend = False

    def get_possible_values(self) -> t.Type[t.Any] | t.List[t.Any]:
        return datetime.datetime

    def get_auto_value(
        self, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[datetime.datetime] | None:
        if user is not None:
            now = datetime.datetime.now(user.timezone)
        else:
            now = datetime.datetime.now()

        return ValueLabel[datetime.datetime](
            value=now,
            label="⏰ " + now.strftime("%m/%d/%Y %H:%M:%S"),
        )

    def serialize_value(self, value: ValueLabel[datetime.datetime]) -> str:
        return value.value.isoformat()

    def deserialize_value(self, serialized: str) -> ValueLabel[datetime.datetime]:
        return ValueLabel[datetime.datetime](
            value=datetime.datetime.fromisoformat(serialized),
            label="⏰ " + datetime.datetime.fromisoformat(serialized).strftime("%m/%d/%Y %H:%M:%S"),
        )


class RelativeTimestampType(QuestionType):
    type = "relative_timestamp"

    def __init__(self, **data):
        super().__init__(**data)

        self._auto = False
        self._must_depend = False
        # TODO: make translatable
        self.value_hint = "Примеры: 2, значит 2 часа назад; 3 дня, 2:12, значит 3 дня 2 часа 12 минут назад. Полный фомат: [ДД дня/день/дней, ][ЧЧ[:ММ[:СС]]"

    @staticmethod
    def _parse_duration(value: str) -> datetime.timedelta:
        """
        Parse a duration string and return a datetime.timedelta.
        """
        duration_re = re.compile(
            r"^"
            r"(?:(?P<days>-?\d+) (?:дня|дней|день)(, )?)?"
            r"((?:(?P<hours>-?\d{1,2}):?)(?=\d{2}|\d+:\d+|$))?"
            r"(?:(?P<minutes>-?\d+):?)?"
            r"(?P<seconds>-?\d+)?"
            # r"(?:\.(?P<microseconds>\d{1,6})\d{0,6})?"
            r"$"
        )

        try:
            match = duration_re.match(value)
        except TypeError:
            raise TypeError("invalid type; expected string")

        if not match:
            raise UnsupportedAnswerError()

        kw = match.groupdict()

        if kw.get("hours") and kw["hours"].startswith("-"):
            if kw.get("minutes"):
                kw["minutes"] = "-" + kw["minutes"]
            if kw.get("seconds"):
                kw["seconds"] = "-" + kw["seconds"]

        if kw.get("days") and kw["days"].startswith("-"):
            if kw.get("hours"):
                kw["hours"] = "-" + kw["hours"]
            if kw.get("minutes"):
                kw["minutes"] = "-" + kw["minutes"]
            if kw.get("seconds"):
                kw["seconds"] = "-" + kw["seconds"]

        kw_ = {k: float(v) for k, v in kw.items() if v is not None}

        return datetime.timedelta(**kw_)

    def get_possible_values(self) -> t.Type[t.Any] | t.List[t.Any]:
        return datetime.datetime

    def get_value_from_answer(
        self, answer: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[datetime.datetime] | None:

        delta = RelativeTimestampType._parse_duration(answer)

        if user is not None:
            now = datetime.datetime.now(user.timezone) - delta
        else:
            now = datetime.datetime.now() - delta

        return ValueLabel[datetime.datetime](
            value=now,
            label="⏰ " + now.strftime("%m/%d/%Y %H:%M:%S"),
        )

    def get_answer_options(
        self, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> t.List[ValueLabel[str]] | None:
        # TODO: make translatable
        return [ValueLabel[str](value="0", label="Только что"), ValueLabel[str](value="1", label="Час назад")]

    def serialize_value(self, value: ValueLabel[datetime.datetime]) -> str:
        return value.value.isoformat()

    def deserialize_value(self, serialized: str) -> ValueLabel[datetime.datetime]:
        return ValueLabel[datetime.datetime](
            value=datetime.datetime.fromisoformat(serialized),
            label="⏰ " + datetime.datetime.fromisoformat(serialized).strftime("%m/%d/%Y %H:%M:%S"),
        )
