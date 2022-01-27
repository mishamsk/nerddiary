import pytest

from .data.crypto import EncryptionProdiver
from .data.data import DataProvider
from .poll.poll import Poll
from .user.user import User


def pytest_collection_modifyitems(items):
    for item in items:
        if "performance" in item.nodeid:
            item.add_marker(pytest.mark.performance)


@pytest.fixture(scope="module")
def test_data_provider(tmp_path_factory):
    data_path = tmp_path_factory.mktemp("data")
    return DataProvider.get_data_provider("sqllite", {"base_path": str(data_path)})


@pytest.fixture(scope="module")
def test_encryption_provider():
    return EncryptionProdiver("test passwrod")


@pytest.fixture(scope="module")
def mockuser():
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
    user = User(
        id="123",
        username="test_user",
        encrypt_data=True,
        password="simple password",
        lang_code="ru",
        timezone="Europe/Moscow",
        polls=[p],
        reports=[],
    )
    return user


@pytest.fixture(scope="module")
def test_data_connection(mockuser, test_data_provider, test_encryption_provider):
    return test_data_provider.get_connection(mockuser.id, test_encryption_provider)
