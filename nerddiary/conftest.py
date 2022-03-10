import pytest

from .data.data import DataProvider
from .poll.poll import Poll
from .user.user import User


def pytest_collection_modifyitems(items):
    for item in items:
        if "performance" in item.nodeid:
            item.add_marker(pytest.mark.performance)


@pytest.fixture
def interrupt_with_sigal(capfd):
    import signal

    def _interrupt_with_sigal(func, run_time: int, signal: signal.Signals = signal.SIGINT, *args, **kwargs):
        from multiprocessing import Process
        from os import kill
        from time import sleep

        p = Process(target=func, args=args, kwargs=kwargs)
        p.start()
        sleep(run_time)
        if p.pid:
            kill(p.pid, signal)
        else:
            raise RuntimeError("Failed to run the process")

        while p.is_alive():
            sleep(0.1)

        captured = capfd.readouterr()
        return (p.exitcode, captured.out, captured.err)

    return _interrupt_with_sigal


@pytest.fixture(scope="class")
def test_data_path(tmp_path_factory):
    return tmp_path_factory.mktemp("data")


@pytest.fixture(scope="class")
def test_data_provider(test_data_path):
    return DataProvider.get_data_provider("sqllite", {"base_path": str(test_data_path)})


@pytest.fixture(scope="class")
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
                "display_name": "When did it start?",
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
                "display_name": "Has it finished?",
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
                "display_name": "What type of headache was it?",
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
                "display_name": "What drug did you use?",
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
                "display_name": "What dose?",
                "description": "Choose among provided drugs or select none if you did not take any",
                "depends_on": "drug_type"
            }
        ]
    }
    """

    return Poll.parse_raw(json)


@pytest.fixture(scope="class")
def mockuser(mockpoll):
    user = User(
        id="123",
        username="test_user",
        lang_code="ru",
        timezone="Europe/Moscow",
        polls=[mockpoll],
    )
    return user


@pytest.fixture(scope="class")
def test_data_connection(mockuser, test_data_provider: DataProvider):
    return test_data_provider.get_connection(mockuser.id, "test password")
