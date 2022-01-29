""" User model """

from __future__ import annotations

from datetime import tzinfo

from pydantic import BaseModel
from pydantic.fields import Field

from ..poll.poll import Poll
from ..primitive.timezone import TimeZone
from ..report.report import Report

from typing import List, Optional


class User(BaseModel):
    id: str = Field(description="This user id", regex=r"^\w{1,64}$")
    username: str | None = Field(default=None, description="Optional user name")
    lang_code: str = Field(
        default="en", min_length=2, max_length=2, description="User preferred language (2 letter code)"
    )
    timezone: Optional[TimeZone]
    polls: Optional[List[Poll]]
    reports: Optional[List[Report]]

    class Config:
        title = "User Configuration"
        extra = "forbid"
        json_encoders = {tzinfo: lambda t: str(t)}

    def __init__(self, **data) -> None:
        super().__init__(**data)

        # convert_reminder_times_to_local_if_set
        if self.polls:
            for poll in self.polls:
                if poll.reminder_time:
                    poll.reminder_time = poll.reminder_time.replace(tzinfo=self.timezone)
