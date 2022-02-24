from pathlib import Path

from nerddiary.bots.tgbot.config import NerdDiaryTGBotConfig

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch


def test_corect_load(monkeypatch: MonkeyPatch, tmp_path: Path, remove_env):
    env_file = tmp_path / ".env"
    monkeypatch.chdir(tmp_path)
    env_file.write_text(
        f"""
        NERDDY_TGBOT_API_ID='api_id_test'
        NERDDY_TGBOT_API_HASH='api_hash_test'
        NERDDY_TGBOT_BOT_TOKEN='bot_token_test'
        NERDDY_TGBOT_BOT_DEBUG=True
        NERDDY_TGBOT_SERVER='https://127.0.0.1:443'
        NERDDY_TGBOT_SESSION_NAME='test_name'
        NERDDY_TGBOT_SESSION_PATH={str(tmp_path)}
        NERDDY_TGBOT_ADMINS='["123"]'
        NERDDY_TGBOT_ALLOWED_USERS='["234","567"]'
        NERDDY_TGBOT_SESSION_UPDATE_TIMEOUT = 5.5
        """
    )

    conf = NerdDiaryTGBotConfig()  # type:ignore
    assert conf.API_ID.get_secret_value() == "api_id_test"
    assert conf.API_HASH.get_secret_value() == "api_hash_test"
    assert conf.BOT_TOKEN.get_secret_value() == "bot_token_test"
    assert conf.BOT_DEBUG is True
    assert conf.SERVER.host == "127.0.0.1" and conf.SERVER.port == "443"
    assert conf.SESSION_NAME == "test_name"
    assert conf.SESSION_PATH == tmp_path
    assert conf.ADMINS == {123}
    assert conf.ALLOWED_USERS == {234, 567}
    assert conf.SESSION_UPDATE_TIMEOUT == 5.5


def test_validations(monkeypatch: MonkeyPatch, tmp_path: Path, remove_env):
    env_file = tmp_path / ".env"
    monkeypatch.chdir(tmp_path)

    # Missing tokens, Incorrect server host & port, empty allowed_users, no admins
    env_file.write_text(
        """
        NERDDY_TGBOT_SERVER='https://127.0.0.1:1020'
        NERDDY_TGBOT_ALLOWED_USERS='[]'
        """
    )

    with pytest.raises(ValidationError) as err:
        NerdDiaryTGBotConfig()  # type:ignore
    assert err.type == ValidationError

    must_error = {
        "API_ID",
        "API_HASH",
        "BOT_TOKEN",
        "SERVER",
        "ADMINS",
        "ALLOWED_USERS",
    }
    for v_err in err.value.errors():
        match v_err["loc"]:
            case ("API_ID",) as mtch:
                assert v_err["type"] == "value_error.missing"
                must_error.remove(mtch[0])
            case ("API_HASH",) as mtch:
                assert v_err["type"] == "value_error.missing"
                must_error.remove(mtch[0])
            case ("BOT_TOKEN",) as mtch:
                assert v_err["type"] == "value_error.missing"
                must_error.remove(mtch[0])
            case ("SERVER",) as mtch:
                assert (
                    v_err["type"] == "value_error"
                    and v_err["msg"] == "Unexpected server port v.port='1020'. Expecting 80 or 443"
                )
                must_error.remove(mtch[0])
            case ("ADMINS",) as mtch:
                assert v_err["type"] == "value_error.missing"
                must_error.remove(mtch[0])
            case ("ALLOWED_USERS",) as mtch:
                assert v_err["type"] == "value_error.set.min_items"
                must_error.remove(mtch[0])
            case _ as mtch:
                assert False, f"Unexpected error caught: {str(mtch)}"

    # all errors caught
    assert len(must_error) == 0
