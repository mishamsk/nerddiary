from nerddiary.core.poll.primitives import ValueLabel

import pytest
from pydantic import ValidationError


class TestValueLabel:
    def test_missing_label(self):
        with pytest.raises(ValidationError) as err:
            ValueLabel.parse_raw('{"value":1}')

        assert err.type is ValidationError
        assert err.value.errors()[0]["type"] == "value_error.missing"

    def test_auto_value(self):
        value = "100"
        vl = ValueLabel(label=value)

        assert vl.value == value

    def test_shorthand_format(self):
        value = "100"
        label = "Super 100"
        vl = ValueLabel.parse_raw('{"' + value + '":"' + label + '"}')

        assert vl.value == value
        assert vl.label == label

    def test_shorthand_format_type_check(self):
        value = 100
        label = 200
        with pytest.raises(ValidationError) as err:
            ValueLabel.parse_raw('{"' + str(value) + '":' + str(label) + "}")

        assert err.type is ValidationError
        assert err.value.errors()[0]["type"] == "assertion_error"
