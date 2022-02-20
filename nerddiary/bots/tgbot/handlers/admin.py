""" Start command handler """
from __future__ import annotations

import asyncio
import logging

from telethon import events, functions, types

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..bot import NerdDiaryTGBot


async def init(bot: NerdDiaryTGBot, logger: logging.Logger):
    # Add admin commands
    logger.debug("Adding admin bot commands")
    to_add = []
    commands = await bot.bot(functions.bots.GetBotCommandsRequest(scope=types.BotCommandScopeDefault(), lang_code="en"))

    commands.append(types.BotCommand(command="reload_ndc", description="Reload NDC"))
    commands.append(types.BotCommand(command="debug_info", description="Debug Info"))

    for admin in bot.config.ADMINS:
        peer = await bot.bot.get_input_entity(admin)
        to_add.append(
            bot.bot(
                functions.bots.SetBotCommandsRequest(
                    scope=types.BotCommandScopePeer(peer=peer),
                    lang_code="en",
                    commands=commands,
                )
            )
        )
    await asyncio.gather(*to_add)

    @bot.bot.on(events.NewMessage(chats=bot.config.ADMINS, pattern=r"^\/reload_ndc"))
    async def reload_ndc(event: events.NewMessage.Event):
        logger.debug(f"Recieved event <{str(event)}>. Processing")
        if not bot.ndc.closed:
            logger.debug("NDC is not closed. Closing")
            await bot.ndc.aclose()

        logger.debug("Starting NDC")
        await bot.ndc.astart()

    @bot.bot.on(events.NewMessage(chats=bot.config.ADMINS, pattern=r"^\/debug_info"))
    async def debug_info(event: events.NewMessage.Event):
        logger.debug(f"Recieved event <{str(event)}>. Processing")

        await event.respond("Expected message routes: " + str(bot._expected_message_route))
        await event.respond("Sessions" + str(bot.ndc._sessions))
