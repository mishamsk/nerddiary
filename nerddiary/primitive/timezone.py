""" Model primitives """

from __future__ import annotations

import datetime

import pytz


class TimeZone(datetime.tzinfo):  # pragma: no cover
    """Custom pydantic type wrapper for timezone"""

    @classmethod
    def __get_validators__(cls):
        # one or more validators may be yielded which will be called in the
        # order to validate the input, each validator will receive as an input
        # the value returned from the previous validator
        yield cls.validate

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(
            type="TzInfo",
        )

    @classmethod
    def validate(cls, v):
        if not isinstance(v, str) and not isinstance(v, datetime.tzinfo):
            raise TypeError("Valid timezone string or tzinfo object required")

        if isinstance(v, str):
            try:
                tz = pytz.timezone(v)
            except pytz.UnknownTimeZoneError:
                raise ValueError("invalid timezone code")

            return tz
        else:
            return v

    def __repr__(self):
        return f"TzInfo({super().__repr__()})"
