""" Poll models """

from __future__ import annotations

import datetime
import logging

from pydantic import BaseModel, validator
from pydantic.fields import Field, PrivateAttr

from .type import DependantSelectType, QuestionType, SelectType

from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Question(BaseModel):
    """Represents a single question within a poll"""

    type: str | SelectType | DependantSelectType | QuestionType = Field(
        description="Question type name or an inline unnamed type (must be either a SelectType or DependantSelectType)"
    )
    """Question type name or an inline unnamed type (must be either a SelectType or DependantSelectType)
    """

    code: str = Field(
        description="Question mandatory short code name. Use it in depends_on", max_length=16, regex=r"^[\da-z_]{1,16}$"
    )
    """Question mandatory short code name. Use it in depends_on
    """

    display_name: str = Field(description="Question short display name - what the user will be asked")
    """Question short display name - what the user will be asked
    """

    description: Optional[str] = Field(description="Question optional long description")
    """Question optional long description
    """

    ephemeral: Optional[bool] = Field(
        default=False,
        description="Whether the answer to this question should not end up in the stored data. Use for branching/delaying without storing the question-answer itself",
    )
    """Whether the answer to this question should not end up in the stored data. Use for branching/delaying without storing the question-answer itself"""

    depends_on: Optional[str] = Field(description="Question name on which this question select or value depends")
    """Question name on which this question select or value depends"""

    delay_time: Optional[datetime.timedelta] = Field(
        description="If `delay_on` is set => this is the timedelta for reminder"
    )
    """ If `delay_on` is set => this is the timedelta for reminder """

    delay_on: Optional[List[str]] = Field(
        description="Value that will trigger a reminder and pause poll. This is the serialized value and not a user `answer` string!"
    )
    """ Value that will trigger a reminder and pause poll. This is the serialized value and not a user `answer` string! """

    default_value: Optional[str] = Field(
        description="Default value. It will be used if this question skipped. This is the serialized value and not a user `answer` string!"
    )
    """ Default value. It will be used if this question skipped. This is the serialized value and not a user `answer` string! """

    skip_on: Optional[Dict[str, str]] = Field(
        description="Dictionary of values:question_code. For each pair, if an answer produced the given value, then the poll will proceed directly to the question_code, potentially skipping all questions in between. This is the serialized value and not a user `answer` string!"
    )
    """ Dictionary of values:question_code. For each pair, if an answer produced the given value, then the poll will proceed directly to the question_code, potentially skipping all questions in between. This is the serialized value and not a user `answer` string! """

    _order: int = PrivateAttr(default=-1)
    _type: QuestionType = PrivateAttr(default=-1)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

        # Replace type name with actual type object
        if isinstance(self.type, str):
            self._type = QuestionType.supported_types[self.type]()
        else:
            self._type = self.type

    @validator("delay_on")
    def check_delay_time_if_delay_on(cls, v, values: Dict[str, Any]):
        if not values["delay_time"] and v:
            raise ValueError("`dalay_time` must be set for `delay_on` questions")

        return v

    @validator("delay_on")
    def check_delay_on_value_exist(cls, v: List[str], values: Dict[str, Any]):
        # Type has not been substitued yet, so have to get it from supported_types
        if isinstance(values["type"], str):
            type_cls = QuestionType.supported_types.get(values["type"])
            type = type_cls() if type_cls else None
        else:
            type = values["type"]

        if type and v:
            pos_values = type.get_possible_values()

            if isinstance(pos_values, list):
                serialized_pos_values = list(map(type.serialize_value, pos_values))
                if any(delay_value not in serialized_pos_values for delay_value in v):
                    raise ValueError(f"`dalay_on` value doesn't exist for the type {type.__class__}")
            else:
                try:
                    if any(not isinstance(type.deserialize_value(delay_value).value, pos_values) for delay_value in v):
                        raise ValueError(f"`dalay_on` value is not compatible with <{type.type}>")
                except Exception:
                    raise ValueError(f"`dalay_on` value is not compatible with <{type.type}>")

        return v

    @validator("default_value")
    def check_default_value_exist(cls, v: str, values: Dict[str, Any]):
        # Type has not been substitued yet, so have to get it from supported_types
        if isinstance(values["type"], str):
            type_cls = QuestionType.supported_types.get(values["type"])
            type = type_cls() if type_cls else None
        else:
            type = values["type"]

        if type and v:
            pos_values = type.get_possible_values()

            if isinstance(pos_values, list):
                serialized_pos_values = list(map(type.serialize_value, pos_values))
                if v not in serialized_pos_values:
                    raise ValueError(f"`default_value` value doesn't exist for the type {type.__class__}")
            else:
                try:
                    if not isinstance(type.deserialize_value(v).value, pos_values):
                        raise ValueError(f"`default_value` value is not compatible with <{type.type}>")
                except Exception:
                    raise ValueError(f"`default_value` value is not compatible with <{type.type}>")

        return v

    @validator("skip_on")
    def check_skip_on_value_exist(cls, v: Dict[str, str], values: Dict[str, Any]):
        # Type has not been substitued yet, so have to get it from supported_types
        if isinstance(values["type"], str):
            type_cls = QuestionType.supported_types.get(values["type"])
            type = type_cls() if type_cls else None
        else:
            type = values["type"]

        if type and v:
            pos_values = type.get_possible_values()

            if isinstance(pos_values, list):
                serialized_pos_values = list(map(type.serialize_value, pos_values))
                if any(delay_value not in serialized_pos_values for delay_value in v):
                    raise ValueError(f"`skip_on` value doesn't exist for the type {type.__class__}")
            else:
                try:
                    if any(not isinstance(type.deserialize_value(delay_value).value, pos_values) for delay_value in v):
                        raise ValueError(f"`skip_on` value is not compatible with <{type.type}>")
                except Exception:
                    raise ValueError(f"`skip_on` value is not compatible with <{type.type}>")

        return v

    @validator("skip_on")
    def check_skip_on_value_is_not_a_delay_on(cls, v: Dict[str, str], values: Dict[str, Any]):
        if "delay_on" in values and values["delay_on"] and v:
            if any(value in values["delay_on"] for value in v):
                raise ValueError("`skip_on` value cannot be a delay_on value")

        return v

    @validator("default_value")
    def check_default_value_is_not_a_delay_on(cls, v: Dict[str, str], values: Dict[str, Any]):
        if "delay_on" in values and values["delay_on"] and v:
            if v in values["delay_on"]:
                raise ValueError("`default_value` value cannot be a delay_on value")

        return v

    @validator("type")
    def validate_named_type_exists(cls, v: str | SelectType | DependantSelectType):
        if isinstance(v, str) and v not in QuestionType.supported_types:
            raise ValueError(f"Type <{v}> is not supported")

        return v
