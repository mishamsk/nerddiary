""" ValueLabel primitive """

from __future__ import annotations

from pydantic import root_validator
from pydantic.generics import GenericModel

from typing import Any, Dict, Generic, TypeVar

ValueType = TypeVar("ValueType")


class ValueLabel(GenericModel, Generic[ValueType]):
    label: str
    value: ValueType

    @root_validator(pre=True)
    def check_and_convert_value_label_dict(cls, values: Dict[Any, Any]):
        if len(values) > 2:  # pragma: no cover
            raise ValueError(
                'Valuelabel may only be defined in either {"value": value, "label": label} or {"value": "label"} formats'
            )

        if len(values) == 1 and "label" not in values and "value" not in values:
            val, lab = next(iter(values.items()))

            assert isinstance(lab, str), "Label must be a string"
            values = {"value": val, "label": lab}

        return values

    class Config:
        frozen = True
        arbitrary_types_allowed = True
