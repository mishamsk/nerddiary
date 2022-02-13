""" Session base abstracct model """

from __future__ import annotations

import enum
import json

from pydantic import BaseModel

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session.session import UserSessionStatus


def generate_notification(type: NotificationType, data: Schema = None) -> str:
    return json.dumps({"notification": str(type), "data": data.dict() if data else None})


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
    key: bytes | None = None
