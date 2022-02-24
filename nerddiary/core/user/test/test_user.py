from nerddiary.core.poll.poll import Poll
from nerddiary.core.user.user import User

import pytest
import pytz
from pydantic import ValidationError


class TestUser:
    def test_correct_json_parse(self, mockpoll: Poll):
        json = """
        {
            "id":"123ABC",
            "username":"best_username",
            "lang_code":"ru",
            "timezone": "Europe/Moscow",
            "polls": [{
                "poll_name": "Headache",
                "command": "head",
                "description": "Headache poll!",
                "reminder_time": "20:00",
                "once_per_day": "true",
                "hours_over_midgnight": 2,
                "questions": [
                    {
                        "type": "relative_timestamp",
                        "code": "start_time",
                        "name": "When did it start?",
                        "description": "Type in how many hours ago did it start aching"
                    },
                    {
                        "type": {
                            "select": [
                                {"No": "😭 No"},
                                {"Yes": "😀 Yes"}
                            ]
                        },
                        "code": "finished",
                        "name": "Has it finished?",
                        "description": "If you still experience headche - answer No and I will ask again in 3 hours",
                        "ephemeral": true,
                        "delay_time": 2,
                        "delay_on": ["No"]
                    },
                    {
                        "type": {
                            "select": [
                                {"tension": "😬 Tension"},
                                {"migraine": "😰 Migraine"},
                                {"other": "🤷‍♀️ Other"}
                            ]
                        },
                        "code": "headache_type",
                        "name": "What type of headache was it?",
                        "description": "Choose among provided headache types"
                    },
                    {
                        "type": {
                            "select": [
                                {"ibuprofen": "😬 Tension"},
                                {"nurtec": "😰 Migraine"},
                                {"none": "🤷‍♀️ Other"}
                            ]
                        },
                        "code": "drug_type",
                        "name": "What drug did you use?",
                        "description": "Choose among provided drugs or select none if you did not take any"
                    },
                    {
                        "type": {
                            "select": {
                                "ibuprofen": [
                                    {"200": "💊 200"},
                                    {"400": "💊💊 400"}
                                ],
                                "nurtec": [
                                    {"1": "💊 1"},
                                    {"2": "💊💊 2"}
                                ],
                                "none": [
                                    {"0": "No 💊 today!"}
                                ]
                            }
                        },
                        "code": "drug_dose",
                        "name": "What dose?",
                        "description": "Choose among provided drugs or select none if you did not take any",
                        "depends_on": "drug_type"
                    }
                ]
            }],
            "reports": [{"name": "test"}]
        }
        """

        u = User.parse_raw(json)

        assert u.id == "123ABC"
        assert u.username == "best_username"
        assert u.lang_code == "ru"
        assert u.timezone == pytz.timezone("Europe/Moscow")
        assert u.polls
        assert len(u.polls) == 1
        assert u.reports
        assert len(u.reports) == 1

        # pydantic equality doesn't check timezone for datefields, otherwise this would fail without mockpoll.reminder_time = mockpoll.reminder_time.replace(tzinfo=u.timezone)
        assert u.polls[0] == mockpoll
        assert u.polls[0].reminder_time.tzinfo == u.timezone

        # Check serialization / de-serialization
        nj = u.json(ensure_ascii=False)
        assert User.parse_raw(nj) == u

        json = """
        {
            "id":"123ABCD"
        }
        """

        u = User.parse_raw(json)

        assert u.id == "123ABCD"
        assert u.username is None
        assert u.lang_code == "en"
        assert u.timezone is None
        assert not u.polls
        assert not u.reports

        # Check serialization / de-serialization
        nj = u.json(ensure_ascii=False)
        assert User.parse_raw(nj) == u

    def test_validations(self):
        # space in id, 3 letter lang_code. unknown timezone. bad poll
        json = """
        {
            "id":"123 ABC",
            "lang_code":"rus",
            "timezone": "Europe/PARTY",
            "polls": [{
                "poll_name": "Headache",
                "command": "head",
                "description": "Headache poll!",
                "reminder_time": "20:00",
                "once_per_day": "true",
                "hours_over_midgnight": 2,
                "questions": [
                ]
            }]
        }
        """

        with pytest.raises(ValidationError) as err:
            User.parse_raw(json)
        assert err.type == ValidationError

        must_error = {
            "id",
            "lang_code",
            "timezone",
            ("polls", 0, "questions"),
        }
        for v_err in err.value.errors():
            match v_err["loc"]:
                case ("id",) as mtch:
                    assert v_err["type"] == "value_error.str.regex"
                    must_error.remove(mtch[0])
                case ("lang_code",) as mtch:
                    assert v_err["type"] == "value_error.any_str.max_length"
                    must_error.remove(mtch[0])
                case ("timezone",) as mtch:
                    assert v_err["type"] == "value_error"
                    must_error.remove(mtch[0])
                case ("polls", 0, "questions") as mtch:
                    assert v_err["type"] == "value_error.list.min_items"
                    must_error.remove(mtch)
                case _ as mtch:
                    assert False, f"Unexpected error caught: {str(mtch)}"

        # all errors caught
        assert len(must_error) == 0

        # polls & reports exist but empty
        json = """
        {
            "id":"123",
            "polls": [],
            "reports": []
        }
        """

        with pytest.raises(ValidationError) as err:
            User.parse_raw(json)
        assert err.type == ValidationError

        must_error = {
            "polls",
            "reports",
        }
        for v_err in err.value.errors():
            match v_err["loc"]:
                case ("polls",) as mtch:
                    assert v_err["type"] == "value_error.list.min_items"
                    must_error.remove(mtch[0])
                case ("reports",) as mtch:
                    assert v_err["type"] == "value_error.list.min_items"
                    must_error.remove(mtch[0])
                case _ as mtch:
                    assert False, f"Unexpected error caught: {str(mtch)}"

        # all errors caught
        assert len(must_error) == 0

        # duplicate poll name
        json = """
        {
            "id":"123ABC",
            "polls": [{
                "poll_name": "Headache",
                "questions": [
                    {
                        "type": "relative_timestamp",
                        "code": "start_time",
                        "name": "When did it start?"
                    }
                ]
            },
            {
                "poll_name": "Headache",
                "questions": [
                    {
                        "type": "relative_timestamp",
                        "code": "start_time",
                        "name": "When did it start?"
                    }
                ]
            }
            ],
            "reports": [{"name": "test"}]
        }
        """

        with pytest.raises(ValidationError) as err:
            User.parse_raw(json)
        assert err.type == ValidationError

        must_error = {
            "polls",
        }
        for v_err in err.value.errors():
            match v_err["loc"]:
                case ("polls",) as mtch:
                    assert v_err["type"] == "value_error" and v_err["msg"] == "Poll names must be unique"
                    must_error.remove(mtch[0])
                case _ as mtch:
                    assert False, f"Unexpected error caught: {str(mtch)}"

        # all errors caught
        assert len(must_error) == 0
