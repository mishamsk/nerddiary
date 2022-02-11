import asyncio

from nerddiary.bots.tgbot.bot import NerdDiaryTGBot

from telethon import TelegramClient


class TestCommands:
    async def test_start(self, test_client: TelegramClient):
        bot = NerdDiaryTGBot()
        me = (await bot.astart())._me

        await test_client.send_message(me.username, "/start")
        await asyncio.sleep(1)
