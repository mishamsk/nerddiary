""" Start command handler """
from __future__ import annotations

import logging

from telethon import custom, events

from ..strings import START_NEW_USER_WELCOME

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..bot import NerdDiaryTGBot


async def init(bot: NerdDiaryTGBot, logger: logging.Logger):
    @bot.bot.on(events.NewMessage(chats=bot.config.ALLOWED_USERS, pattern=r"^\/start"))
    async def start(event: custom.Message):
        logger.debug(f"Recieved event <{str(event)}>. Processing")
        await event.respond(START_NEW_USER_WELCOME, reply_to=event.reply_to_msg_id)
        session = await bot.ndc.get_session(event.sender_id)
        await event.respond(str(session))
        if session:
            res = await bot.ndc.unlock_session(session=session, password="password")
            if res:
                await event.respond("Unlocked too!")
