import asyncio
import logging

from telethon import TelegramClient
from telethon.tl.types import User

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
        self._me = None

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
    def me(self) -> User | None:
        return self._me  # type: ignore

    async def _astart(self):
        self._logger.debug("Starting NerdDiary TG Bot")
        asyncio.create_task(self._ndc.astart())
        await self._bot.start(bot_token=self._bot_config.BOT_TOKEN.get_secret_value())  # type:ignore
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
