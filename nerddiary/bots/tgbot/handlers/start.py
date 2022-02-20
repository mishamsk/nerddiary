""" Start command handler """
from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from nerddiary.core.client.rpc import RPCError
from nerddiary.core.server.rpc import RPCErrors
from nerddiary.core.server.schema import PollBaseSchema
from nerddiary.core.server.session.status import UserSessionStatus

from telethon import events, functions, types

from ..strings import SERVER_ERROR

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from ..bot import NerdDiaryTGBot


def _(text: str):
    return text


START_NEW_USER_WELCOME = _(
    "Привет! Я - бот дневник. Буду помогать записывать то, что тебе нужно.\nЯ очень серьезно отношусь к приватности информации, поэтому все, что ты запишешь будет храниться в зашифрованном виде. Никто, включая меня и моих создателей, не сможет получить доступ. \nДля того, чтобы я мог зашифровать информацию, мне нужен пароль.\n *Очень важно не потерять этот пароль, так как без него, все записи будут потеряны безвозвратно!*\nВведи пароль..."
)
START_EXISTING_USER_WELCOME = _(
    "Привет, с возвращением! Либо ты меня отключал, либо меня перезагрузили. Придется ввести пароль заново..."
)
START_ACTIVE_USER_RESPONSE = _("И снова здравствуйте! Я уже запущен, так что можно не нажимать /start")
START_NEW_USING_PASSWORD = _("Спасибо!")
START_LOCKED_TRYING_PASSWORD = _("Спасибо! Проверяю пароль...")
START_LOCKED_INCORRECT_PASSWORD = _("Неправильный пароль. Попробуй еще раз...")
START_UNLOCKED_CONFIG_REQUEST = _("Теперь пришли мне файл с настройками.")
START_UNLOCKED_CONFIG_MISSING = _("Ты забыл приложить файл.")
START_UNLOCKED_CONFIG_WRONG_TYPE = _("Файл должен быть типа json! Попробуй другой.")
START_UNLOCKED_CONFIG_INCORRECT = _("Что-то не то с конфигурацией! Попробуй другой.")
START_CONFIGURED = _("Отлично! Теперь я готов к работе.")

ROUTE_PASSWORD_PROMPT = "/start/password_prompt"
ROUTE_CONFIGURATION_PROMPT = "/start/config_prompt"


async def init(bot: NerdDiaryTGBot, logger: logging.Logger):
    @bot.bot.on(events.NewMessage(chats=bot.config.ALLOWED_USERS, pattern=r"^\/start"))
    async def start(event: events.NewMessage.Event):
        logger.debug(f"Recieved event <{str(event)}>. Processing")
        session = await bot.ndc.get_session(str(event.sender_id))
        if not session:
            await event.respond(SERVER_ERROR)
        else:
            if session.user_status == UserSessionStatus.NEW:
                await event.respond(START_NEW_USER_WELCOME)
                if not bot.set_expected_message_route(str(event.sender_id), ROUTE_PASSWORD_PROMPT):
                    await event.respond(SERVER_ERROR)
                else:
                    raise events.StopPropagation
            elif session.user_status == UserSessionStatus.LOCKED:
                await event.respond(START_EXISTING_USER_WELCOME)
                if not bot.set_expected_message_route(str(event.sender_id), ROUTE_PASSWORD_PROMPT):
                    await event.respond(SERVER_ERROR)
                else:
                    raise events.StopPropagation
            elif session.user_status == UserSessionStatus.UNLOCKED:
                await event.respond(START_UNLOCKED_CONFIG_REQUEST)
                if not bot.set_expected_message_route(str(event.sender_id), ROUTE_CONFIGURATION_PROMPT):
                    await event.respond(SERVER_ERROR)
            else:
                await event.respond(START_ACTIVE_USER_RESPONSE)

    @bot.bot.on(
        events.NewMessage(
            chats=bot.config.ALLOWED_USERS,
            pattern=r"^[^\/].*",
            func=lambda e: bot.get_expected_message(str(e.sender_id)) == ROUTE_PASSWORD_PROMPT,
        )
    )
    async def unlock(event: events.NewMessage.Event):
        logger.debug(f"Recieved event <{str(event)}>. Processing")
        session = await bot.ndc.get_session(str(event.sender_id))

        if not session:
            await event.respond(SERVER_ERROR)
            return
        else:
            if session.user_status == UserSessionStatus.NEW:
                await event.respond(START_NEW_USING_PASSWORD)

                res = await bot.ndc.exec_api_method(
                    method="unlock_session", user_id=session.user_id, password=event.message.message
                )

                if res != "True":
                    await event.respond(SERVER_ERROR)
                    return
            elif session.user_status == UserSessionStatus.LOCKED:
                await event.respond(START_LOCKED_TRYING_PASSWORD)
                res = False
                try:
                    res = await bot.ndc.exec_api_method(
                        method="unlock_session", user_id=session.user_id, password=event.message.message
                    )
                    pass
                except RPCError as r_err:
                    if r_err.code == RPCErrors.SESSION_INCORRECT_PASSWORD_OR_KEY:
                        await event.respond(START_LOCKED_INCORRECT_PASSWORD)
                        return

                if res != "True":
                    await event.respond(SERVER_ERROR)
                    return

            logger.debug("Waiting for user status to update after unlock")
            wait = 0
            while not session.user_status > UserSessionStatus.LOCKED and wait < bot.config.SESSION_UPDATE_TIMEOUT:
                wait += 1
                await asyncio.sleep(1)
                session = await bot.ndc.get_session(str(event.sender_id))

            if not session.user_status > UserSessionStatus.LOCKED:
                await event.respond(SERVER_ERROR)
                return

            bot.clear_expected_message_route(str(event.sender_id), ROUTE_PASSWORD_PROMPT)

            if session.user_status == UserSessionStatus.UNLOCKED:
                await event.respond(START_UNLOCKED_CONFIG_REQUEST)
                if not bot.set_expected_message_route(str(event.sender_id), ROUTE_CONFIGURATION_PROMPT):
                    await event.respond(SERVER_ERROR)
                else:
                    raise events.StopPropagation

    @bot.bot.on(
        events.NewMessage(
            chats=bot.config.ALLOWED_USERS,
            pattern=r"^[^\/].*",
            func=lambda e: bot.get_expected_message(str(e.sender_id)) == ROUTE_CONFIGURATION_PROMPT,
        )
    )
    async def config(event: events.NewMessage.Event):
        logger.debug(f"Recieved event <{str(event)}>. Processing")
        session = await bot.ndc.get_session(str(event.sender_id))

        if not session:
            await event.respond(SERVER_ERROR)
            return

        if not event.file:
            await event.respond(START_UNLOCKED_CONFIG_MISSING)
            return

        if not event.file.mime_type == "application/json":
            await event.respond(START_UNLOCKED_CONFIG_WRONG_TYPE)
            return

        config = BytesIO()
        await bot.bot.download_media(event.message, file=config)

        try:
            await bot.ndc.exec_api_method(
                method="set_config", user_id=session.user_id, config=config.getvalue().decode()
            )
        except RPCError:
            await event.respond(START_UNLOCKED_CONFIG_INCORRECT)
            return

        bot.clear_expected_message_route(str(event.sender_id), ROUTE_CONFIGURATION_PROMPT)

        polls: List[Dict[str, Any]] = await bot.ndc.exec_api_method(method="get_polls", user_id=session.user_id)

        if polls:
            commands = await bot.bot(
                functions.bots.GetBotCommandsRequest(scope=types.BotCommandScopeDefault(), lang_code="en")
            )

            for poll in polls:
                poll = PollBaseSchema.parse_obj(poll)
                commands.append(types.BotCommand(command=poll.command, description=poll.description or poll.poll_name))

            await bot.bot(
                functions.bots.SetBotCommandsRequest(
                    scope=types.BotCommandScopePeer(peer=await event.get_input_chat()),
                    lang_code="en",
                    commands=commands,
                )
            )

        await event.respond(START_CONFIGURED)
