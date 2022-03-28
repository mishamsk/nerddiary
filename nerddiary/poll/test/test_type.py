from nerddiary.poll.type import (
    AuroTimestampType,
    DependantSelectType,
    QuestionType,
    SelectType,
    TimestampType,
    UnsupportedAnswerError,
)
from nerddiary.primitive.valuelabel import ValueLabel

import arrow
import pytest
import pytz
from pydantic import ValidationError


class Mockuser:
    def __init__(self) -> None:
        self.timezone = pytz.timezone("US/Eastern")
        self.lang_code = "en"


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
        assert vl1 in select.get_possible_values()
        assert vl2 in select.get_possible_values()
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

        assert select.serialize_value(vl1) == "No"

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
        wrong_dependency_2 = AuroTimestampType()

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
        vl_yes_1 = ValueLabel(value="YesNo", label="😀 No")
        vl_yes_2 = ValueLabel(value="YesYes", label="😭 Yes")

        select = DependantSelectType.parse_raw(json)

        assert select.type is None
        assert vl_no_1 in select.get_possible_values()
        assert vl_no_2 in select.get_possible_values()
        assert vl_yes_1 in select.get_possible_values()
        assert vl_yes_2 in select.get_possible_values()
        assert len(select.get_possible_values()) == 4
        assert select.is_auto is False
        assert select.is_dependent is True

        # No dep value
        with pytest.raises(AttributeError) as err:
            select.get_value_from_answer("Other value")
        assert err.type == AttributeError

        # Wrong dep value type
        with pytest.raises(AttributeError) as err:
            select.get_value_from_answer("Other value", ValueLabel(label="label", value=1))  # type: ignore
        assert err.type == AttributeError

        # Correct dep value, wrong answer value
        with pytest.raises(UnsupportedAnswerError) as err:
            select.get_value_from_answer("Other value", ValueLabel(label="label", value="No"))
        assert err.type == UnsupportedAnswerError

        # Wrong dep value, correct answer value
        with pytest.raises(AttributeError) as err:
            select.get_value_from_answer("NoNo", ValueLabel(label="label", value="Other value"))
        assert err.type == AttributeError

        with pytest.raises(NotImplementedError) as err:
            select.get_auto_value()
        assert err.type == NotImplementedError

        # Wrong dep value type
        with pytest.raises(AttributeError) as err:
            select.get_answer_options(ValueLabel(label="label", value="Other value"))
        assert err.type == AttributeError

        assert select.get_answer_options(ValueLabel(label="label", value="No")) == [vl_no_1, vl_no_2]

        assert select.serialize_value(vl_no_1) == "NoNo"

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
    def test_correct_function(self):

        time = AuroTimestampType()

        assert time.type == "auto_timestamp"
        assert time.is_auto is True
        assert time.is_dependent is False
        assert time.get_possible_values() == arrow.Arrow

        with pytest.raises(NotImplementedError) as err:
            time.get_value_from_answer("answer")
        assert err.type == NotImplementedError

        with pytest.raises(NotImplementedError) as err:
            time.get_answer_options()
        assert err.type == NotImplementedError

        with pytest.raises(NotImplementedError) as err:
            time.get_answer_options()
        assert err.type == NotImplementedError

        mockuser = Mockuser()

        tz = mockuser.timezone

        now_unaware = arrow.now().replace(microsecond=0)
        now_aware = arrow.now(tz).replace(microsecond=0)
        assert time.get_auto_value().value.replace(microsecond=0) == now_unaware
        assert time.get_auto_value(user=mockuser).value.replace(microsecond=0) == now_aware  # type:ignore

        assert time.serialize_value(ValueLabel(value=now_aware, label="Smth")) == now_aware.isoformat()

        assert time.check_dependency_type(AuroTimestampType()) is False


class TestRelativeTimestampType:
    def test_correct_function(self):

        time = TimestampType()

        assert time.type == "timestamp"
        assert time.is_auto is False
        assert time.is_dependent is False
        assert time.get_possible_values() == arrow.Arrow

        # Checking value conversion
        mockuser = Mockuser()

        tz = mockuser.timezone

        # Unsupported value
        assert time.get_value_from_answer("answer") is None

        # Testing various time delta format parsing
        now_aware = arrow.now(tz).replace(microsecond=0)
        assert time.get_value_from_answer("an hour ago", user=mockuser).value.replace(microsecond=0) == now_aware.shift(  # type: ignore
            hours=-1
        )

        assert time.get_value_from_answer("a day ago", user=mockuser).value.replace(  # type: ignore
            microsecond=0
        ) == now_aware.shift(  # type: ignore
            days=-1
        )

        # Other methods
        with pytest.raises(NotImplementedError) as err:
            time.get_auto_value()
        assert err.type == NotImplementedError

        assert time.serialize_value(ValueLabel(value=now_aware, label="Smth")) == now_aware.isoformat()

        assert time.check_dependency_type(AuroTimestampType()) is False
