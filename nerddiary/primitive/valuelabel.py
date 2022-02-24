""" ValueLabel primitive """

from __future__ import annotations

from pydantic import BaseModel, root_validator, validator

from typing import Any, Dict


class ValueLabel(BaseModel):
    label: str
    value: Any = None

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

    @validator(
        "value",
        always=True,
    )
    def set_value_to_label_if_empty(
        cls,
        v: str,
        values: Dict[str, Any],
    ):
        return v if v is not None else values.get("label")
