from datetime import datetime, timedelta

from nerddiary.poll.type import (
    DependantSelectType,
    QuestionType,
    RelativeTimestampType,
    SelectType,
    TimestampType,
    UnsupportedAnswerError,
)
from nerddiary.primitive.valuelabel import ValueLabel

import pytest
from pydantic import ValidationError


class TestQuestionType:
    def test_abstract(self):
        with pytest.raises(TypeError, match=r"Can't instantiate abstract class.*"):
            QuestionType()  # type: ignore

    def test_supported_types(self):
        types = QuestionType.supported_types
        assert len(types) > 0


class TestSelectType:
    def test_correct_json_parse(self):
        json = """
        {
            "select": [
                {"No": "😀 No"},
                {"Yes": "😭 Yes"}
            ]
        }
        """
        vl1 = ValueLabel(value="No", label="😀 No")
        vl2 = ValueLabel(value="Yes", label="😭 Yes")

        select = SelectType.parse_raw(json)

        assert select.type is None
        assert "No" in select.get_possible_values()
        assert "Yes" in select.get_possible_values()
        assert len(select.get_possible_values()) == 2
        assert select.is_auto is False
        assert select.is_dependent is False

        with pytest.raises(UnsupportedAnswerError) as err:
            select.get_value_from_answer("Other value")
        assert err.type == UnsupportedAnswerError

        with pytest.raises(NotImplementedError) as err:
            select.get_auto_value()
        assert err.type == NotImplementedError

        assert select.get_answer_options() == [vl1, vl2]

        assert select.get_serializable_value(vl1) == "No"

        assert select.check_dependency_type(SelectType.parse_raw(json)) is False

    def test_validations(self):
        # select should be of ValueType supported dicts
        json = """
        {
            "select": [
                {"No": 1},
                {"Yes": "😭 Yes"}
            ]
        }
        """

        with pytest.raises(ValidationError) as err:
            SelectType.parse_raw(json)
        assert err.type == ValidationError

        # empty select not allowed
        json = """
        {
            "select": [
            ]
        }
        """

        with pytest.raises(ValidationError) as err:
            SelectType.parse_raw(json)
        assert err.type == ValidationError


class TestDependantSelectType:
    def test_correct_json_parse(self):
        json = """
        {
            "select": [
                {"No": "😀 No"},
                {"Yes": "😭 Yes"}
            ]
        }
        """
        proper_dependency = SelectType.parse_raw(json)

        json = """
        {
            "select": [
                {"Other": "😀 No"},
                {"Another": "😭 Yes"}
            ]
        }
        """
        wrong_dependency_1 = SelectType.parse_raw(json)
        wrong_dependency_2 = TimestampType()

        json = """
        {
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
        """
        vl_no_1 = ValueLabel(value="NoNo", label="😀 No")
        vl_no_2 = ValueLabel(value="NoYes", label="😭 Yes")
        # vl_yes_1 = ValueLabel(value="YesNo", label="😀 No")
        # vl_yes_2 = ValueLabel(value="YesYes", label="😭 Yes")

        select = DependantSelectType.parse_raw(json)

        assert select.type is None
        assert "NoNo" in select.get_possible_values()
        assert "NoYes" in select.get_possible_values()
        assert "YesNo" in select.get_possible_values()
        assert "YesYes" in select.get_possible_values()
        assert len(select.get_possible_values()) == 4
        assert select.is_auto is False
        assert select.is_dependent is True

        # No dep value
        with pytest.raises(AttributeError) as err:
            select.get_value_from_answer("Other value")
        assert err.type == AttributeError

        # Wrong dep value type
        with pytest.raises(AttributeError) as err:
            select.get_value_from_answer("Other value", 1)
        assert err.type == AttributeError

        # Correct dep value, wrong answer value
        with pytest.raises(UnsupportedAnswerError) as err:
            select.get_value_from_answer("Other value", "No")
        assert err.type == UnsupportedAnswerError

        # Wrong dep value, correct answer value
        with pytest.raises(AttributeError) as err:
            select.get_value_from_answer("NoNo", "Other value")
        assert err.type == AttributeError

        with pytest.raises(NotImplementedError) as err:
            select.get_auto_value()
        assert err.type == NotImplementedError

        # Wrong dep value type
        with pytest.raises(AttributeError) as err:
            select.get_answer_options("Other value")
        assert err.type == AttributeError

        assert select.get_answer_options("No") == [vl_no_1, vl_no_2]

        assert select.get_serializable_value(vl_no_1) == "NoNo"

        assert select.check_dependency_type(wrong_dependency_1) is False
        assert select.check_dependency_type(wrong_dependency_2) is False
        assert select.check_dependency_type(proper_dependency) is True

    def test_validations(self):
        # select should be of ValueType supported dicts
        json = """
        {
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
        """

        with pytest.raises(ValidationError) as err:
            SelectType.parse_raw(json)
        assert err.type == ValidationError

        # empty select not allowed
        json = """
        {
            "select": {
            }
        }
        """

        with pytest.raises(ValidationError) as err:
            SelectType.parse_raw(json)
        assert err.type == ValidationError

        # empty sub select not allowed
        json = """
        {{
            "select": {
                "No": [
                ],
                "Yes": [
                    {"YesNo": "😀 No"},
                    {"YesYes": "😭 Yes"}
                ]
            }
        }
        """

        with pytest.raises(ValidationError) as err:
            SelectType.parse_raw(json)
        assert err.type == ValidationError


class TestTimestampType:
    def test_correct_function(self, mockuser):

        time = TimestampType()

        assert time.type == "timestamp"
        assert time.is_auto is True
        assert time.is_dependent is False
        assert time.get_possible_values() == datetime

        with pytest.raises(NotImplementedError) as err:
            time.get_value_from_answer("answer")
        assert err.type == NotImplementedError

        with pytest.raises(NotImplementedError) as err:
            time.get_answer_options()
        assert err.type == NotImplementedError

        with pytest.raises(NotImplementedError) as err:
            time.get_answer_options()
        assert err.type == NotImplementedError

        tz = mockuser.timezone

        now_unaware = datetime.now().replace(microsecond=0)
        now_aware = datetime.now(tz).replace(microsecond=0)
        assert time.get_auto_value().value.replace(microsecond=0) == now_unaware
        assert time.get_auto_value(user=mockuser).value.replace(microsecond=0) == now_aware  # type:ignore

        assert time.get_serializable_value(ValueLabel(value=now_aware, label="Smth")) == now_aware.isoformat()

        assert time.check_dependency_type(TimestampType()) is False


class TestRelativeTimestampType:
    def test_correct_function(self, mockuser):

        time = RelativeTimestampType()

        assert time.type == "relative_timestamp"
        assert time.is_auto is False
        assert time.is_dependent is False
        assert time.get_possible_values() == datetime

        # Checking value conversion
        tz = mockuser.timezone

        # Unsupported value
        with pytest.raises(UnsupportedAnswerError) as err:
            time.get_value_from_answer("answer")
        assert err.type == UnsupportedAnswerError

        # Testing various time delta format parsing
        now_aware = datetime.now(tz).replace(microsecond=0)
        assert time.get_value_from_answer("1", user=mockuser).value.replace(microsecond=0) == now_aware - timedelta(
            hours=1
        )

        assert time.get_value_from_answer("1:12", user=mockuser).value.replace(microsecond=0) == now_aware - timedelta(
            hours=1, minutes=12
        )

        assert time.get_value_from_answer("1 день", user=mockuser).value.replace(
            microsecond=0
        ) == now_aware - timedelta(days=1)

        assert time.get_value_from_answer("1 день, 2:12:31", user=mockuser).value.replace(
            microsecond=0
        ) == now_aware - timedelta(days=1, hours=2, minutes=12, seconds=31)

        assert time.get_value_from_answer("-1", user=mockuser).value.replace(microsecond=0) == now_aware + timedelta(
            hours=1
        )

        assert time.get_value_from_answer("-1:12", user=mockuser).value.replace(microsecond=0) == now_aware + timedelta(
            hours=1, minutes=12
        )

        assert time.get_value_from_answer("-1 день", user=mockuser).value.replace(
            microsecond=0
        ) == now_aware + timedelta(days=1)

        assert time.get_value_from_answer("-1 день, 2:12:31", user=mockuser).value.replace(
            microsecond=0
        ) == now_aware + timedelta(days=1, hours=2, minutes=12, seconds=31)

        # And one test with unaware
        now_unaware = datetime.now().replace(microsecond=0)

        assert time.get_value_from_answer("1 день, 2:12:31").value.replace(microsecond=0) == now_unaware - timedelta(
            days=1, hours=2, minutes=12, seconds=31
        )

        # Other methods
        assert time.get_answer_options() is None

        with pytest.raises(NotImplementedError) as err:
            time.get_auto_value()
        assert err.type == NotImplementedError

        assert time.get_serializable_value(ValueLabel(value=now_aware, label="Smth")) == now_aware.isoformat()

        assert time.check_dependency_type(TimestampType()) is False
