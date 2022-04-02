""" Poll models for question types """

from __future__ import annotations

import abc
import datetime
import logging

import arrow
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

    def get_answer_from_value(
        self, value: ValueLabel, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> str:
        """Raises UnsupportedAnswerError() if string answer value is not supported"""
        if self.is_auto:
            raise NotImplementedError("This type doesn't support user input")

        return self.serialize_value(value)

    def get_auto_value(self, dep_value: ValueLabel | None = None, user: User | None = None) -> ValueLabel | None:
        if not self.is_auto:
            raise NotImplementedError("This type doesn't auto generate a value")

    @abc.abstractmethod
    def serialize_value(self, value: ValueLabel) -> str:
        pass  # pragma: no cover

    @abc.abstractmethod
    def deserialize_value(
        self, serialized: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel:
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

    def deserialize_value(
        self, serialized: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[str]:
        candidates = [vl for vl in self.select if vl.value == serialized]
        if not candidates:
            raise ValueError()

        return candidates[0]

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
        self, answer: str, dep_value: ValueLabel[str] | None = None, user: User | None = None
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

    def deserialize_value(
        self, serialized: str, dep_value: ValueLabel[str] | None = None, user: User | None = None
    ) -> ValueLabel[str]:
        if not dep_value:
            raise AttributeError(
                "<deserialize_value> called without a dependent value for a question with dependent select list"
            )
        if not isinstance(dep_value.value, str):
            raise AttributeError(
                f"<deserialize_value> called with incorrect dependency value. Got {dep_value.value}, expected a string"
            )
        if dep_value.value not in self.select:
            raise AttributeError(
                f"<deserialize_value> called with incorrect dependency value. Got {dep_value}, but it doesn't exist among this type's select"
            )

        candidates = [vl for vl in self.select[dep_value.value] if vl.value == serialized]
        if not candidates:
            raise ValueError()

        return candidates[0]

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


class AuroTimestampType(QuestionType):
    type = "auto_timestamp"

    def __init__(self, **data):
        super().__init__(**data)

        self._auto = True
        self._must_depend = False

    def get_possible_values(self) -> t.Type[t.Any] | t.List[t.Any]:
        return arrow.Arrow

    def get_auto_value(
        self, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[arrow.Arrow] | None:

        now = arrow.now(user.timezone if user else None)

        return ValueLabel[arrow.Arrow](
            value=now,
            label="⏰ " + now.format("DD MMM, YYYY HH:mm", locale=user.lang_code if user else "en"),
        )

    def serialize_value(self, value: ValueLabel[arrow.Arrow]) -> str:
        return value.value.for_json()

    def deserialize_value(
        self, serialized: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[arrow.Arrow]:
        time = arrow.get(serialized)

        return ValueLabel[arrow.Arrow](
            value=time,
            label="⏰ " + time.format("DD MMM, YYYY HH:mm", locale=user.lang_code if user else "en"),
        )


class TimestampType(QuestionType):
    type = "timestamp"

    def __init__(self, **data):
        super().__init__(**data)

        self._auto = False
        self._must_depend = False
        # TODO: make translatable
        self.value_hint = "Дата (можно с временем) в формате: 2021-01-30 [14:00:15] или период относительно текущего времени:  2 часа назад"

    def get_possible_values(self) -> t.Type[t.Any] | t.List[t.Any]:
        return arrow.Arrow

    def get_value_from_answer(
        self, answer: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[arrow.Arrow] | None:

        time = None
        try:
            time = arrow.get(answer, locale=user.lang_code if user else "en")
        except arrow.ParserError:
            pass

        if time is None:
            try:
                time = arrow.now(user.timezone if user else None).dehumanize(
                    answer, locale=user.lang_code if user else "en"
                )
            except ValueError:
                pass

        if time is None:
            return None

        return ValueLabel[arrow.Arrow](
            value=time,
            label="⏰ " + time.format("DD MMM, YYYY HH:mm", locale=user.lang_code if user else "en"),
        )

    def get_answer_from_value(
        self, value: ValueLabel[arrow.Arrow], dep_value: ValueLabel | None = None, user: User | None = None
    ) -> str:
        """Raises UnsupportedAnswerError() if string answer value is not supported"""

        return value.value.format("YYYY-MM-DDTHH:mm:ss")

    @property
    def allows_manual(self) -> bool:
        """Returns True if question type allows arbitrary manual value as input"""
        return True

    def get_answer_options(
        self, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> t.List[ValueLabel[str]] | None:
        now_str = arrow.get().humanize(locale=user.lang_code if user else "en")
        hour_ago_str = arrow.get().shift(hours=-1).humanize(locale=user.lang_code if user else "en")
        return [ValueLabel[str](value=now_str, label=now_str), ValueLabel[str](value=hour_ago_str, label=hour_ago_str)]

    def serialize_value(self, value: ValueLabel[arrow.Arrow]) -> str:
        return value.value.for_json()

    def deserialize_value(
        self, serialized: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[arrow.Arrow]:
        time = arrow.get(serialized)

        return ValueLabel[arrow.Arrow](
            value=time,
            label="⏰ " + time.format("DD MMM, YYYY HH:mm", locale=user.lang_code if user else "en"),
        )


class TimeType(QuestionType):
    type = "time"

    def __init__(self, **data):
        super().__init__(**data)

        self._auto = False
        self._must_depend = False
        # TODO: make translatable
        self.value_hint = "Время в формате (можно с секундаами): 14:00[:15]"

    def get_possible_values(self) -> t.Type[t.Any] | t.List[t.Any]:
        return datetime.time

    def get_value_from_answer(
        self, answer: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[datetime.time] | None:

        tm = None
        try:
            tm = datetime.time.fromisoformat(answer)
        except ValueError:
            pass

        if tm is None:
            return None

        return ValueLabel[datetime.time](
            value=tm,
            label="⏰ " + tm.isoformat(timespec="seconds"),
        )

    @property
    def allows_manual(self) -> bool:
        """Returns True if question type allows arbitrary manual value as input"""
        return True

    def get_answer_options(
        self, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> t.List[ValueLabel[str]] | None:
        now_str = arrow.now(tz=user.timezone if user else None).time().isoformat(timespec="seconds")
        hour_ago_str = (
            arrow.now(tz=user.timezone if user else None).shift(hours=-1).time().isoformat(timespec="seconds")
        )
        return [ValueLabel[str](value=now_str, label=now_str), ValueLabel[str](value=hour_ago_str, label=hour_ago_str)]

    def serialize_value(self, value: ValueLabel[datetime.time]) -> str:
        return value.value.isoformat(timespec="seconds")

    def deserialize_value(
        self, serialized: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[datetime.time]:
        time = datetime.time.fromisoformat(serialized)

        return ValueLabel[datetime.time](
            value=time,
            label="⏰ " + time.isoformat(timespec="seconds"),
        )


class TextType(QuestionType):
    type = "text"

    def __init__(self, **data):
        super().__init__(**data)

        self._auto = False
        self._must_depend = False
        # TODO: make translatable
        self.value_hint = "Произвольный текст"

    def get_possible_values(self) -> t.Type[t.Any] | t.List[t.Any]:
        return str

    def get_value_from_answer(
        self, answer: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel | None:
        return ValueLabel[str](
            value=answer,
            label=answer,
        )

    def serialize_value(self, value: ValueLabel[str]) -> str:
        return value.value

    def deserialize_value(
        self, serialized: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[str]:
        return ValueLabel[str](
            value=serialized,
            label=serialized,
        )


class FloatType(QuestionType):
    type = "float"

    def __init__(self, **data):
        super().__init__(**data)

        self._auto = False
        self._must_depend = False
        # TODO: make translatable
        self.value_hint = "Число с плавающей точкой"

    def get_possible_values(self) -> t.Type[t.Any] | t.List[t.Any]:
        return float

    def get_value_from_answer(
        self, answer: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel | None:
        value = 0.0
        try:
            value = float(answer)
        except ValueError:
            raise UnsupportedAnswerError(f"Couldn't convert {answer=} to float")

        return ValueLabel[float](
            value=value,
            label=answer,
        )

    def serialize_value(self, value: ValueLabel[str]) -> str:
        return str(value.value)

    def deserialize_value(
        self, serialized: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[float]:
        return ValueLabel[float](
            value=float(serialized),
            label=serialized,
        )


class IntType(QuestionType):
    type = "int"

    def __init__(self, **data):
        super().__init__(**data)

        self._auto = False
        self._must_depend = False
        # TODO: make translatable
        self.value_hint = "Любое целое число"

    def get_possible_values(self) -> t.Type[t.Any] | t.List[t.Any]:
        return int

    def get_value_from_answer(
        self, answer: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel | None:
        value = 0
        try:
            value = int(answer)
        except ValueError:
            raise UnsupportedAnswerError(f"Couldn't convert {answer=} to int")

        return ValueLabel[int](
            value=value,
            label=answer,
        )

    def serialize_value(self, value: ValueLabel[str]) -> str:
        return str(value.value)

    def deserialize_value(
        self, serialized: str, dep_value: ValueLabel | None = None, user: User | None = None
    ) -> ValueLabel[int]:
        return ValueLabel[int](
            value=int(serialized),
            label=serialized,
        )
