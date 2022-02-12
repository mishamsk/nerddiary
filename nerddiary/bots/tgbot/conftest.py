import asyncio
import os

from nerddiary.bots.tgbot.config import NerdDiaryTGBotConfig

import pytest
from telethon import TelegramClient
from telethon.sessions import StringSession


@pytest.fixture
def remove_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NERDDY_TGBOT_API_ID", raising=False)
    monkeypatch.delenv("NERDDY_TGBOT_API_HASH", raising=False)
    monkeypatch.delenv("NERDDY_TGBOT_BOT_TOKEN", raising=False)
    monkeypatch.delenv("NERDDY_TGBOT_BOT_DEBUG", raising=False)
    monkeypatch.delenv("NERDDY_TGBOT_admins", raising=False)
    monkeypatch.delenv("NERDDY_TGBOT_allowed_users", raising=False)


@pytest.fixture
async def test_client(event_loop: asyncio.AbstractEventLoop):
    TEST_SESSION = os.getenv("NERDDY_TGBOT_TEST_SESSION")
    assert TEST_SESSION

    conf = NerdDiaryTGBotConfig()

    client = TelegramClient(
        StringSession(TEST_SESSION), int(conf.API_ID.get_secret_value()), conf.API_HASH.get_secret_value()
    )

    try:
        await client.start()  # type:ignore
        yield client
    finally:
        client.disconnect()