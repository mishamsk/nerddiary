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
def mockpoll():
    json = """
    {
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
    }
    """

    return Poll.parse_raw(json)


@pytest.fixture(scope="module")
def mockuser(mockpoll):
    user = User(
        id="123",
        username="test_user",
        lang_code="ru",
        timezone="Europe/Moscow",
        polls=[mockpoll],
        reports=[],
    )
    return user


@pytest.fixture(scope="module")
def test_data_connection(mockuser, test_data_provider, test_encryption_provider):
    return test_data_provider.get_connection(mockuser.id, test_encryption_provider)
