from datetime import timedelta

from nerddiary.poll.question import Question
from nerddiary.poll.type import AuroTimestampType, DependantSelectType
from nerddiary.primitive.valuelabel import ValueLabel

import pytest
from pydantic import ValidationError


class TestQuestion:
    def test_correct_json_parse(self):
        json = """
        {
            "code":"q",
            "display_name":"name",
            "description": "some description",
            "type": {
                "select": {
                    "No": [
                        {"NoNo": "😀 No"},
                        {"NoYes": "😭 Yes"}
                    ],
                    "Yes": [
                        {"YesNo": "😀 No"},
                        {"YesYes": "😭 Yes"}
                    ]
                }
            }
        }
        """

        vl_no_1 = ValueLabel(value="NoNo", label="😀 No")
        vl_no_2 = ValueLabel(value="NoYes", label="😭 Yes")
        vl_yes_1 = ValueLabel(value="YesNo", label="😀 No")
        vl_yes_2 = ValueLabel(value="YesYes", label="😭 Yes")

        q = Question.parse_raw(json)

        assert isinstance(q._type, DependantSelectType)
        assert q.code == "q"
        assert q.display_name == "name"
        assert q.description == "some description"
        assert q.ephemeral is False
        assert q.depends_on is None
        assert q.delay_time is None
        assert q.delay_on is None
        assert q._order == -1
        assert vl_no_1 in q._type.get_possible_values()
        assert vl_no_2 in q._type.get_possible_values()
        assert vl_yes_1 in q._type.get_possible_values()
        assert vl_yes_2 in q._type.get_possible_values()

        # Check serialization / de-serialization
        nj = q.json(ensure_ascii=False)
        assert Question.parse_raw(nj) == q

        json = """
        {
            "code":"q",
            "display_name": "not code",
            "type": "auto_timestamp"
        }
        """

        q = Question.parse_raw(json)

        assert isinstance(q._type, AuroTimestampType)
        assert q.code == "q"
        assert q.display_name == "not code"
        assert q.description is None
        assert q.ephemeral is False
        assert q.depends_on is None
        assert q.delay_time is None
        assert q.delay_on is None
        assert q._order == -1

        # Check serialization / de-serialization
        nj = q.json(ensure_ascii=False)
        assert Question.parse_raw(nj) == q

        json = """
        {
            "code":"q2",
            "display_name": "not code",
            "type": {
                "select": {
                    "No": [
                        {"NoNo": "😀 No"},
                        {"NoYes": "😭 Yes"}
                    ],
                    "Yes": [
                        {"YesNo": "😀 No"},
                        {"YesYes": "😭 Yes"}
                    ]
                }
            },
            "depends_on": "other q",
            "ephemeral": "True",
            "delay_on": ["NoNo"],
            "delay_time": "10:15"

        }
        """

        q = Question.parse_raw(json)

        assert isinstance(q._type, DependantSelectType)
        assert q.ephemeral is True
        assert q.depends_on == "other q"
        assert q.delay_time == timedelta(minutes=10, seconds=15)
        assert q.delay_on == ["NoNo"]

        # Check serialization / de-serialization
        nj = q.json(ensure_ascii=False)
        assert Question.parse_raw(nj) == q

    def test_validations(self):
        # missing code
        json = """
        {
            "display_name": "not code",
            "description": "some description",
            "type": {
                "select": {
                    "No": [
                        {"NoNo": "😀 No"},
                        {"NoYes": "😭 Yes"}
                    ],
                    "Yes": [
                        {"YesNo": "😀 No"},
                        {"YesYes": "😭 Yes"}
                    ]
                }
            }
        }
        """

        with pytest.raises(ValidationError) as err:
            Question.parse_raw(json)
        assert err.type == ValidationError
        assert "code" in err.value.errors()[0]["loc"]
        assert err.value.errors()[0]["type"] == "value_error.missing"

        # broken select inline type
        json = """
        {
            "code": "q",
            "display_name": "not code",
            "type": {
                "select": {
                    "No": [
                        {"NoNo": 1},
                        {"NoYes": "😭 Yes"}
                    ],
                    "Yes": [
                        {"YesNo": "😀 No"},
                        {"YesYes": "😭 Yes"}
                    ]
                }
            }
        }
        """

        with pytest.raises(ValidationError) as err:
            Question.parse_raw(json)
        assert err.type == ValidationError
        assert "type" in err.value.errors()[0]["loc"]
        assert err.value.errors()[0]["type"] == "type_error.str"

        # unknown named type
        json = """
        {
            "code": "q",
            "display_name": "not code",
            "type": "what is this type?"
        }
        """

        with pytest.raises(ValidationError) as err:
            Question.parse_raw(json)
        assert err.type == ValidationError
        assert "type" in err.value.errors()[0]["loc"]
        assert err.value.errors()[0]["msg"] == "Type <what is this type?> is not supported"

        # delay time missing
        json = """
        {
            "code": "q",
            "display_name": "not code",
            "type": {
                "select": {
                    "No": [
                        {"NoNo": "😀 No"},
                        {"NoYes": "😭 Yes"}
                    ],
                    "Yes": [
                        {"YesNo": "😀 No"},
                        {"YesYes": "😭 Yes"}
                    ]
                }
            },
            "delay_on": ["NoNo"]
        }
        """

        with pytest.raises(ValidationError) as err:
            Question.parse_raw(json)
        assert err.type == ValidationError
        assert "delay_on" in err.value.errors()[0]["loc"]
        assert err.value.errors()[0]["msg"] == "`dalay_time` must be set for `delay_on` questions"

        # delay on - incorrect value for select
        json = """
        {
            "code": "q",
            "display_name": "not code",
            "type": {
                "select": {
                    "No": [
                        {"NoNo": "😀 No"},
                        {"NoYes": "😭 Yes"}
                    ],
                    "Yes": [
                        {"YesNo": "😀 No"},
                        {"YesYes": "😭 Yes"}
                    ]
                }
            },
            "delay_on": ["NoNo and no!"],
            "delay_time": "10:15"
        }
        """

        with pytest.raises(ValidationError) as err:
            Question.parse_raw(json)
        assert err.type == ValidationError
        assert "delay_on" in err.value.errors()[0]["loc"]
        assert "`dalay_on` value doesn't exist for the type" in err.value.errors()[0]["msg"]

        # delay on - incorrect value for auto type
        json = """
        {
            "code": "q",
            "display_name": "not code",
            "type": "timestamp",
            "delay_on": ["NoNo and no!"],
            "delay_time": "10:15"
        }
        """

        with pytest.raises(ValidationError) as err:
            Question.parse_raw(json)
        assert err.type == ValidationError
        assert "delay_on" in err.value.errors()[0]["loc"]
        assert err.value.errors()[0]["msg"] == "`dalay_on` value is not compatible with <timestamp>"
