""" Session base abstracct model """

from __future__ import annotations

import enum
import json

from pydantic import BaseModel

from ..primitive.valuelabel import ValueLabel
from .session.status import UserSessionStatus

from typing import List


def generate_notification(type: NotificationType, data: Schema | None = None) -> str:
    return json.dumps({"notification": str(type.value), "data": data.dict() if data else None})


@enum.unique
class NotificationType(enum.IntEnum):
    SERVER_CLIENT_CONNECTED = 101
    SERVER_CLIENT_DISCONNECTED = 102
    SERVER_SESSION_UPDATE = 103
    SERVER_POLL_DELAY_PASSED = 104
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
    poll_name: str
    command: str
    description: str | None


class PollsSchema(Schema):
    polls: List[PollBaseSchema]


class PollWorkflowSchema(Schema):
    poll_run_id: str


class PollWorkflowStateSchema(Schema):
    poll_run_id: str
    completed: bool
    delayed: bool
    delayed_for: str
    current_question: str
    current_question_index: int
    current_question_description: str | None
    current_question_value_hint: str | None
    current_question_allow_manual_answer: bool
    current_question_select_list: List[ValueLabel[str]] | None
    questions: List[str]
    answers: List[str]
