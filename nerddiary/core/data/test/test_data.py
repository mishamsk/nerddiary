import datetime
import json
import random
import time

from nerddiary.core.data.data import DataConnection, DataProvider, SQLLiteConnection, SQLLiteProvider

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.dialects.sqlite import BLOB


class TestDataProvider:
    def test_abstract(self):
        with pytest.raises(TypeError, match=r"Can't instantiate abstract class.*"):
            DataProvider()  # type: ignore

    def test_supported_providers(self):
        for provider in DataProvider.supported_providers.values():
            assert issubclass(provider, DataProvider)
            # Fail test if subcless is not imported here => probably not tested
            assert provider in globals().values()

    def test_unsupported_provider(self):
        with pytest.raises(NotImplementedError) as err:
            DataProvider.get_data_provider("non_existent_provider", {"base_path_missplled": "test"})
        assert err.type == NotImplementedError


class TestDataConnection:
    def test_abstract(self):
        with pytest.raises(TypeError, match=r"Can't instantiate abstract class.*"):
            DataConnection()  # type: ignore


class TestSQLLiteProvider:
    def test_provider(self, tmp_path_factory):
        assert SQLLiteProvider.name == "sqllite"

        mockuser_id = "123"

        # Incorrect params
        with pytest.raises(ValidationError) as err:
            DataProvider.get_data_provider("sqllite", {"base_path_missplled": "test"})
        assert err.type == ValidationError

        # Correct params
        data_path = tmp_path_factory.mktemp("data")
        provider = DataProvider.get_data_provider("sqllite", {"base_path": str(data_path)})

        assert isinstance(provider, SQLLiteProvider)
        assert provider.check_data_exist(user_id=mockuser_id) is False
        assert provider.check_config_exist(user_id=mockuser_id) is False

        user_data_path = data_path / mockuser_id / "data.db"
        user_data_path.mkdir(parents=True, exist_ok=True)
        user_data_path.touch()
        assert provider.check_data_exist(user_id=mockuser_id) is True

        user_conf_path = data_path / mockuser_id / "config"
        user_conf_path.mkdir(parents=True, exist_ok=True)
        user_conf_path.touch()
        assert provider.check_config_exist(user_id=mockuser_id) is True

    def test_get_connection(self, test_data_provider, test_encryption_provider):
        mockuser_id = "123"

        # Encrypted
        conn = test_data_provider.get_connection(mockuser_id, test_encryption_provider)

        assert isinstance(conn, SQLLiteConnection)
        assert conn.encrypted is True

        # Not Encrypted
        conn = test_data_provider.get_connection(mockuser_id)

        assert isinstance(conn, SQLLiteConnection)
        assert conn.encrypted is False


class TestSQLLiteConnection:
    def test_config(self, mockuser, test_data_provider, test_encryption_provider):
        mockuser_id = "123"

        conn: SQLLiteConnection = test_data_provider.get_connection(mockuser_id, test_encryption_provider)

        config = mockuser.json(exclude_unset=True, ensure_ascii=False)

        assert conn.store_config(config)
        config_path = test_data_provider._params.base_path.joinpath(mockuser_id, "config")

        # Validate data was encrypted
        assert config_path.read_bytes().decode() != config

        # Check correct loading of the config back
        assert conn.load_config() == config

    def test_connection(self, test_data_provider, test_encryption_provider):
        mockuser_id = "123"

        conn: SQLLiteConnection = test_data_provider.get_connection(mockuser_id, test_encryption_provider)

        poll_code_1 = "poll1"
        poll_code_2 = "poll2"
        row_data_base = "some"

        poll_1_values = []
        for i in range(1, 10):
            poll_1_values.append(row_data_base + str(i))
            id = conn.append_log(poll_code_1, row_data_base + str(i))
            assert id == i

        poll_2_values = []
        for i in range(10, 20):
            poll_2_values.append(row_data_base + str(i))
            id = conn.append_log(poll_code_2, row_data_base + str(i))
            assert id == i

        # Test data is encrypted at rest
        engine = sa.create_engine(
            test_data_provider._params._base_uri
            + str(test_data_provider._params.base_path.joinpath(mockuser_id, "data.db"))
        )

        meta = sa.MetaData()

        data_table = sa.Table(
            "data",
            meta,
            sa.Column("id", sa.Integer, primary_key=True, index=True, nullable=False),
            sa.Column("poll_code", sa.String, index=True, unique=False, nullable=False),
            sa.Column("log", BLOB, nullable=False),
            sa.Column("created_ts", sa.DATETIME, nullable=False),
            sa.Column("updated_ts", sa.DATETIME, nullable=False),
        )

        # Check data is indeed encrypted
        with engine.connect() as econn:
            stmt = data_table.select().where(data_table.c.poll_code == poll_code_1)
            result = econn.execute(stmt)

            rows = result.all()
            for row in rows:
                assert row.log.decode() not in poll_1_values

        # Check get_all_logs
        all_logs = conn.get_all_logs()
        assert len(all_logs) == len(poll_1_values) + len(poll_2_values)
        assert set(map(lambda x: x[1], all_logs)) == set(poll_1_values + poll_2_values)

        # Check get_last_n_logs
        test_logs = conn.get_last_n_logs("unknown_poll", 1)
        assert len(test_logs) == 0

        test_logs = conn.get_last_n_logs(poll_code_1, 1)
        assert len(test_logs) == 1
        test_id, test_log = test_logs[0]

        # Check get_logs
        assert conn.get_log(test_id) == (test_id, poll_1_values[0])

        # Check get_logs
        test_logs = conn.get_last_n_logs(poll_code_1, 5)
        assert len(test_logs) == 5

        test_ids = list(map(lambda x: x[0], test_logs))

        assert conn.get_logs(test_ids) == list(zip(test_ids, poll_1_values))

        # Check get_last_logs
        test_logs = conn.get_last_logs(
            poll_code_1,
            date_from=datetime.datetime.now() - datetime.timedelta(days=1),
            max_rows=3,
        )
        assert len(test_logs) == 3

        test_ids = list(map(lambda x: x[0], test_logs))

        assert conn.get_logs(test_ids) == list(zip(test_ids, poll_1_values))

        # Check get_poll_logs
        test_logs = conn.get_poll_logs(
            poll_code_1,
            date_to=datetime.datetime.now() - datetime.timedelta(days=1),
            max_rows=3,
        )
        assert len(test_logs) == 0

        # Check update_log
        test_id, test_log = conn.get_last_n_logs(poll_code_1, 1)[0]
        conn.update_log(test_id, "new data")
        assert conn.get_log(test_id)[1] == "new data"

        # Double check data is still encrypted
        with engine.connect() as econn:
            stmt = data_table.select().where(data_table.c.id == test_id)
            result = econn.execute(stmt)

            rows = result.all()
            for row in rows:
                assert row.log.decode() != "new data"

    def test_performance(self, test_data_connection):
        start_time = time.time()

        for i in range(1, 2500):
            log = json.dumps([i, random.randrange(1, i * 100)])
            test_data_connection.append_log("headache", log)

        runtime = time.time() - start_time
        assert runtime < 5, f"Real runtime: {runtime}"

        start_time = time.time()

        test_data_connection.get_last_logs("headache", datetime.datetime.now() - datetime.timedelta(days=3), 10)

        runtime = time.time() - start_time
        assert runtime < 5, f"Real runtime: {runtime}"
