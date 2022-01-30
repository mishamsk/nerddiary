""" Session base abstracct model """

from __future__ import annotations

from .session import Session


class StringSession(Session):
    async def create_session(self):
        pass

    async def close_session(self):
        pass
