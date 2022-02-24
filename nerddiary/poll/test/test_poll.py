import datetime

from nerddiary.poll.poll import Poll

import pytest
from pydantic import ValidationError


class TestPoll:
    def test_correct_json_parse(self):
        json = """
        {
            "poll_name": "headache",
            "command": "head",
            "description": "Headache poll!",
            "reminder_time": "20:00",
            "once_per_day": "true",
            "hours_over_midgnight": 2,
            "questions": [
                {
                    "code": "q1",
                    "type": {
                        "select": [
                            {"No": "😀 No"},
                            {"Yes": "😭 Yes"}
                        ]
                    }
                },
                {
                    "code": "q2",
                    "depends_on": "q1",
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
            ]
        }
        """

        p = Poll.parse_raw(json)

        assert p.poll_name == "headache"
        assert p.command == "head"
        assert p.description == "Headache poll!"
        assert p.reminder_time == datetime.time(hour=20)
        assert p.once_per_day is True
        assert p.hours_over_midgnight == 2
        assert len(p.questions) == 2
        assert p.questions[0].code == "q1"
        assert p.questions[1].depends_on == "q1"
        assert p._questions_dict["q2"] == p.questions[1]
        assert p.questions[0]._order == 0
        assert p.questions[1]._order == 1

        # Check serialization / de-serialization
        nj = p.json(ensure_ascii=False)
        assert Poll.parse_raw(nj) == p

        json = """
        {
            "poll_name":"tWo woRDs",
            "questions": [
                {
                    "code": "q1",
                    "type": {
                        "select": [
                            {"No": "😀 No"},
                            {"Yes": "😭 Yes"}
                        ]
                    }
                },
                {
                    "code": "q2",
                    "depends_on": "q1",
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
                },
                {
                    "code":"q3",
                    "name": "auto q",
                    "type": "timestamp"
                }

            ]

        }
        """

        p = Poll.parse_raw(json)

        assert p.poll_name == "tWo woRDs"
        assert p.command == "two_words"
        assert p.description is None
        assert p.reminder_time is None
        assert p.once_per_day is True
        assert p.hours_over_midgnight == 3
        assert len(p.questions) == 3
        assert p._questions_dict["q3"] == p.questions[2]
        assert p.questions[2]._order == 2

        # Check serialization / de-serialization
        nj = p.json(ensure_ascii=False)
        assert Poll.parse_raw(nj) == p

        json = """
        {
            "poll_name":"русское имя",
            "questions": [
                {
                    "code":"q3",
                    "name": "auto q",
                    "type": "timestamp"
                }

            ]

        }
        """

        p = Poll.parse_raw(json)

        assert p.poll_name == "русское имя"
        assert p.command is None

        # Check serialization / de-serialization
        nj = p.json(ensure_ascii=False)
        assert Poll.parse_raw(nj) == p

    def test_validations(self):
        # too long name, description. wrong command format. incorrect types for other fiels. Incorrect dependency (depends on undependable type)
        json = """
        {
            "poll_name":"too long of a name. more than 30 characters.",
            "command": "Has Uppercase",
            "description":"Is also waaaay too long of a name. more than 100 characters. And that means a lot of text. And some more. To my hearts extent",
            "reminder_time": "Not time",
            "once_per_day": "WEIRD BOOL",
            "hours_over_midgnight": -1,
            "questions": [
                {
                    "code": "q2",
                    "name": "Can't depend on future question",
                    "depends_on": "q1",
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
                },
                {
                    "code": "q1",
                    "type": {
                        "select": [
                            {"No": "😀 No"},
                            {"Yes": "😭 Yes"}
                        ]
                    }
                },
                {
                    "code":"q3",
                    "name": "Can't depend on q1",
                    "type": "timestamp",
                    "depends_on": "q1"
                }

            ]

        }
        """

        with pytest.raises(ValidationError) as err:
            Poll.parse_raw(json)
        assert err.type == ValidationError

        must_error = {
            "poll_name",
            "command",
            "description",
            "reminder_time",
            "once_per_day",
            "hours_over_midgnight",
            ("questions", 2),
        }
        for v_err in err.value.errors():
            match v_err["loc"]:
                case ("poll_name",) as mtch:
                    assert v_err["type"] == "value_error.any_str.max_length"
                    must_error.remove(mtch[0])
                case ("command",) as mtch:
                    assert v_err["type"] == "value_error.str.regex"
                    must_error.remove(mtch[0])
                case ("description",) as mtch:
                    assert v_err["type"] == "value_error.any_str.max_length"
                    must_error.remove(mtch[0])
                case ("reminder_time",) as mtch:
                    assert v_err["type"] == "value_error.time"
                    must_error.remove(mtch[0])
                case ("once_per_day",) as mtch:
                    assert v_err["type"] == "type_error.bool"
                    must_error.remove(mtch[0])
                case ("hours_over_midgnight",) as mtch:
                    assert v_err["type"] == "value_error.number.not_ge"
                    must_error.remove(mtch[0])
                case ("questions", 2) as mtch:
                    assert (
                        v_err["type"] == "value_error"
                        and v_err["msg"]
                        == "Question <Can't depend on q1> depends on <q1> but is not of a type that can be dependant"
                    )
                    must_error.remove(mtch)
                case _ as mtch:
                    assert False, f"Unexpected error caught: {str(mtch)}"

        # all errors caught
        assert len(must_error) == 0

        # missing poll_name, too long command, hours_over_midgnight with once_per_day = False. Incorrect dependency (depends on later question)
        json = """
        {
            "command": "too long of a command. more than 30 characters.",
            "once_per_day": false,
            "hours_over_midgnight": 3,
            "questions": [
                {
                    "code": "q2",
                    "name": "Can't depend on future question",
                    "depends_on": "q1",
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
                },
                {
                    "code": "q1",
                    "type": {
                        "select": [
                            {"No": "😀 No"},
                            {"Yes": "😭 Yes"}
                        ]
                    }
                }
            ]
        }
        """

        with pytest.raises(ValidationError) as err:
            Poll.parse_raw(json)
        assert err.type == ValidationError

        must_error = {
            "poll_name",
            "command",
            "hours_over_midgnight",
            "questions",
        }
        for v_err in err.value.errors():
            match v_err["loc"]:
                case ("poll_name",) as mtch:
                    assert v_err["type"] == "value_error.missing"
                    must_error.remove(mtch[0])
                case ("command",) as mtch:
                    assert v_err["type"] == "value_error.any_str.max_length"
                    must_error.remove(mtch[0])
                case ("hours_over_midgnight",) as mtch:
                    assert (
                        v_err["type"] == "value_error"
                        and v_err["msg"] == "`hours_over_midgnight` can only be set for `once_per_day` polls"
                    )
                    must_error.remove(mtch[0])
                case ("questions",) as mtch:
                    assert (
                        v_err["type"] == "value_error"
                        and v_err["msg"]
                        == "Question <Can't depend on future question> depends on <q1> which is either not defined, or goes after this question"
                    )
                    must_error.remove(mtch[0])
                case _ as mtch:
                    assert False, f"Unexpected error caught: {str(mtch)}"

        # all errors caught
        assert len(must_error) == 0

        # Incorrect dependency (dependency values do not match dependant options)
        json = """
        {
            "poll_name": "tok",
            "questions": [
                {
                    "code": "q1",
                    "type": {
                        "select": [
                            {"No": "😀 No"},
                            {"Yes": "😭 Yes"}
                        ]
                    }
                },
                {
                    "code": "q2",
                    "depends_on": "q1",
                    "name": "Can't depend on No/Yes select question",
                    "type": {
                        "select": {
                            "No1": [
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
            ]
        }
        """

        with pytest.raises(ValidationError) as err:
            Poll.parse_raw(json)
        assert err.type == ValidationError

        must_error = {
            "questions",
        }
        for v_err in err.value.errors():
            match v_err["loc"]:
                case ("questions",) as mtch:
                    assert (
                        v_err["type"] == "value_error"
                        and v_err["msg"]
                        == "Question <Can't depend on No/Yes select question> is of type that is not compatible with the dependcy question <q1>"
                    )
                    must_error.remove(mtch[0])
                case _ as mtch:
                    assert False, f"Unexpected error caught: {str(mtch)}"

        # all errors caught
        assert len(must_error) == 0
