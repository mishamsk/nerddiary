import asyncio
import logging

from telethon import TelegramClient, functions, types

from ...core.asynctools.asyncapp import AsyncApplication
from ...core.client.client import NerdDiaryClient
from . import handlers
from .config import NerdDiaryTGBotConfig


class NerdDiaryTGBot(AsyncApplication):
    def __init__(
        self,
        *,
        config: NerdDiaryTGBotConfig = None,
        loop: asyncio.AbstractEventLoop = None,
        logger: logging.Logger = logging.getLogger(__name__),
    ) -> None:
        super().__init__(loop=loop, logger=logger)

        if config is None:
            # Load config from env variables or .env file if config is not passed as param
            config = NerdDiaryTGBotConfig()  # type:ignore

        self._bot_config = config

        bot = TelegramClient(
            str(config.SESSION_PATH / config.SESSION_NAME),
            int(config.API_ID.get_secret_value()),
            config.API_HASH.get_secret_value(),
        )
        self._bot = bot
        self._ndc = NerdDiaryClient(logger=logger.getChild("ndc"))
        self._expected_message_lock = asyncio.Lock()
        self._expected_message_route: str | None = None

    @property
    def config(self) -> NerdDiaryTGBotConfig:
        return self._bot_config

    @property
    def bot(self) -> TelegramClient:
        return self._bot

    @property
    def ndc(self) -> NerdDiaryClient:
        return self._ndc

    @property
    def expected_message(self) -> str | None:
        return self._expected_message_route

    async def set_expected_message_route(self, route: str) -> bool:
        async with self._expected_message_lock:
            if self._expected_message_route is not None:
                return False
            else:
                self._expected_message_route = route
                return True

    async def clear_expected_message_route(self, route: str) -> bool:
        async with self._expected_message_lock:
            if self._expected_message_route == route:
                self._expected_message_route = None
                return True
            else:
                return False

    async def _astart(self):
        self._logger.debug("Starting NerdDiary TG Bot")
        asyncio.create_task(self._ndc.astart())
        await self._bot.start(bot_token=self._bot_config.BOT_TOKEN.get_secret_value())  # type:ignore
        # Add standard commands
        self._logger.debug("Adding standard bot commands")
        commands = [
            types.BotCommand(command="start", description="Start bot"),
            types.BotCommand(command="help", description="Помощь"),
        ]

        await self.bot(
            functions.bots.SetBotCommandsRequest(
                scope=types.BotCommandScopeDefault(),
                lang_code="en",
                commands=commands,
            )
        )

        await handlers.init(bot=self, root_logger=self._logger)
        self._me = await self._bot.get_me()

    async def _aclose(self) -> bool:
        self._logger.debug("Closing NerdDiary TG Bot")
        res = await self._ndc.aclose()
        coro = self._bot.disconnect()
        if coro:
            await coro
            return res
        else:
            return False

    async def _arun(self):
        await self._bot.run_until_disconnected()  # type:ignore
