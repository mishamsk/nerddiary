""" Poll models """

from __future__ import annotations

import datetime
import itertools
import logging
import re

from pydantic import BaseModel, validator
from pydantic.fields import Field, PrivateAttr

from .question import Question

from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Poll(BaseModel):
    """Represents a single poll"""

    poll_name: str = Field(max_length=30, description="User facing name")  # type: ignore # noqa: F722
    """ User facing name """

    command: str = Field(default=None, max_length=32, regex=r"^[\da-z_]{1,32}$", description="Command for user call (api or in a bot). If none is given poll_name may be used if it fits the format after replacing whitespace with _")  # type: ignore # noqa: F722

    description: str | None = Field(description="Poll long description", max_length=100)

    reminder_time: Optional[datetime.time] = Field(description="Poll auto-reminder time in user local time zone")
    """ Poll auto-reminder time in user local time zone """

    questions: List[Question] = Field(  # type:ignore
        description="List of polls questions", min_items=1
    )
    """ Dictionary of polls questions """

    _questions_dict: Dict[str, Question] = PrivateAttr(default={})
    """ Dictionary of polls questions for workflow convinience
    """

    once_per_day: bool = Field(default=True, description="Whether this poll can only be asked once a day")
    """ Whether this poll can only be asked once a day """

    hours_over_midgnight: Optional[int] = Field(
        default=3,
        ge=0,
        le=7,
        description="For once per day polls - if poll is started before `hours_over_midgnight`AM set it to previous day 11:59:59PM",
    )
    """ For once per day polls - if poll is started before `hours_over_midgnight`AM set it to previous day 11:59:59PM """

    class Config:
        json_encoders = {Question: lambda q: q.json(exclude_none=True, models_as_dict=False)}

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

        # Strip whitespace
        if self.command:
            self.command.strip()

        # Try auto assign command from name
        if not self.command and re.match(r"^[\da-z_]{1,32}$", re.sub(r"\s+", "_", self.poll_name.lower())):
            self.command = re.sub(r"\s+", "_", self.poll_name.lower())

        # Create help mappings for workflow processing
        self._questions_dict = {}
        for q, order in zip(self.questions, itertools.count()):
            q._order = order
            self._questions_dict |= {q.code: q}

    @validator("questions", each_item=True)
    def dependant_question_type_must_support_it(cls, v: Question):
        # Check that dependant question exists and has already been processed (comes earlier)
        if v.depends_on and not v.type.is_dependent:  # type:ignore
            raise ValueError(
                f"Question <{v.name}> depends on <{v.depends_on}> but is not of a type that can be dependant"
            )

        return v

    @validator("questions")
    def dependant_question_must_exist_and_support_type(cls, v: List[Question]):
        # Check that dependant question exists and has already been processed (comes earlier)
        previous = []
        q_dict: Dict[str, Question] = {}
        for q in v:
            q_dict |= {q.code: q}

        for name, question in q_dict.items():
            if question.depends_on:
                if question.depends_on not in previous:
                    raise ValueError(
                        f"Question <{name}> depends on <{question.depends_on}> which is either not defined, or goes after this question"
                    )

                if not question.type.check_dependency_type(q_dict[question.depends_on].type):  # type: ignore
                    raise ValueError(
                        f"Question <{name}> is of type that can't depend on question <{question.depends_on}>"
                    )

            previous.append(name)

        return v

    @validator("hours_over_midgnight")
    def check_once_per_day(cls, v, values: Dict[str, Any]):
        opd = values.get("once_per_day")
        if opd is not None and not opd and v:
            raise ValueError("`hours_over_midgnight` can only be set for `once_per_day` polls")

        return v
