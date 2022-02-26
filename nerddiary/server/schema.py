""" Session base abstracct model """

from __future__ import annotations

import enum
import json

from pydantic import BaseModel

from .session.status import UserSessionStatus

from typing import Dict, List


def generate_notification(type: NotificationType, data: Schema | None = None) -> str:
    return json.dumps({"notification": str(type.value), "data": data.dict() if data else None})


@enum.unique
class NotificationType(enum.IntEnum):
    CLIENT_CONNECTED = 10
    CLIENT_DISCONNECTED = 20
    SESSION_UPDATE = 30


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


class PollWorkflowStateSchema(Schema):
    poll_run_id: str
    completed: bool
    delayed: bool
    current_question: str
    current_question_description: str
    current_question_value_hint: str
    current_question_allow_manual_answer: bool
    current_question_select_list: Dict[str, str] | None
    questions: List[str]
    answers: List[str]
