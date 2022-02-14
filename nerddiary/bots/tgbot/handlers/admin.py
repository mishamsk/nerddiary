""" Start command handler """
from __future__ import annotations

import asyncio
import logging

from telethon import custom, events, functions, types

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..bot import NerdDiaryTGBot


async def init(bot: NerdDiaryTGBot, logger: logging.Logger):
    # Add admin commands
    logger.debug("Adding admin bot commands")
    to_add = []
    for admin in bot.config.ADMINS:
        peer = await bot.bot.get_input_entity(admin)
        to_add.append(
            bot.bot(
                functions.bots.SetBotCommandsRequest(
                    scope=types.BotCommandScopePeer(peer=peer),
                    lang_code="en",
                    commands=[types.BotCommand(command="reload_ndce", description="Reload NDC")],
                )
            )
        )
    await asyncio.gather(*to_add)

    @bot.bot.on(events.NewMessage(chats=bot.config.ADMINS, pattern=r"^\/reload_ndc"))
    async def reload_ndc(event: custom.Message):
        logger.debug(f"Recieved event <{str(event)}>. Processing")
        if not bot.ndc.closed:
            logger.debug("NDC is not closed. Closing")
            await bot.ndc.aclose()

        logger.debug("Starting NDC")
        await bot.ndc.astart()
