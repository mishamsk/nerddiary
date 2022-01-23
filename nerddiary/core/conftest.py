import pytest
import pytz

from .data.crypto import EncryptionProdiver
from .data.data import DataProvider


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
    class MockUser:
        def __init__(self) -> None:
            self.timezone = pytz.timezone("US/Eastern")
            self.id = 123

    return MockUser()


@pytest.fixture(scope="module")
def test_data_connection(mockuser, test_data_provider, test_encryption_provider):
    # TODO: Redo to get this from mockuser property
    return test_data_provider.get_connection(mockuser, test_encryption_provider)
