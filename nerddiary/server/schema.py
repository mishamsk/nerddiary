""" Session base abstracct model """

from __future__ import annotations

import datetime
import enum
import json

from pydantic import BaseModel
from pydantic.json import pydantic_encoder

from ..primitive.valuelabel import ValueLabel
from .session.status import UserSessionStatus

from typing import Dict, List


def generate_notification(type: NotificationType, data: Schema | None = None) -> str:
    if data:
        return json.dumps(
            {
                "notification": str(type.value),
                "data": {"schema": data.__class__.__name__, "data": data.dict()},
            },
            default=pydantic_encoder,
        )
    else:
        return json.dumps(
            {
                "notification": str(type.value),
                "data": None,
            }
        )


@enum.unique
class NotificationType(enum.IntEnum):
    SERVER_CLIENT_CONNECTED = 101
    SERVER_CLIENT_DISCONNECTED = 102
    SERVER_SESSION_UPDATE = 103
    SERVER_POLL_DELAY_PASSED = 104
    SERVER_POLL_REMINDER = 105
    CLIENT_BEFORE_CONNECT = 201
    CLIENT_ON_CONNECT = 202
    CLIENT_CONNECT_FAILED = 203
    CLIENT_BEFORE_DISCONNECT = 204
    CLIENT_ON_DISCONNECT = 205


class Schema(BaseModel):
    pass


class ClientSchema(Schema):
    client_id: str


class UserSessionSchema(Schema):
    user_id: str
    user_status: UserSessionStatus
    key: str | None = None


class PollBaseSchema(Schema):
    user_id: str
    poll_name: str


class PollExtendedSchema(PollBaseSchema):
    command: str
    description: str | None


class PollsSchema(Schema):
    polls: List[PollExtendedSchema]


class PollLogSchema(Schema):
    id: int | None = None
    poll_name: str
    poll_ts: datetime.datetime
    data: Dict[str, str]


class PollLogsSchema(Schema):
    logs: List[PollLogSchema]


class PollWorkflowSchema(PollBaseSchema):
    poll_run_id: str


class PollWorkflowStateSchema(PollWorkflowSchema):
    completed: bool
    delayed: bool
    delayed_for: str
    poll_ts: datetime.datetime
    current_question_display_name: str
    current_question_code: str
    current_question_description: str | None
    current_question_value_hint: str | None
    current_question_allow_manual_answer: bool
    current_question_select_list: List[ValueLabel[str]] | None
    current_question_default_value: str | None
    questions: List[str]
    answers: List[str]
