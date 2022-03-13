import datetime
import json
import random
import time
from pathlib import Path

from nerddiary.data.crypto import EncryptionProdiver
from nerddiary.data.data import (
    DataConnection,
    DataCorruptionError,
    DataCorruptionType,
    DataProvider,
    IncorrectPasswordKeyError,
    SQLLiteConnection,
    SQLLiteProvider,
    SQLLiteProviderParams,
)
from nerddiary.user.user import User

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.dialects.sqlite import BLOB


class TestDataProvider:
    def test_abstract(self):
        with pytest.raises(TypeError, match=r"Can't instantiate abstract class.*"):
            DataProvider()  # type: ignore

    def test_classmethods(self, test_data_path):
        test_provider = "sqllite"
        test_params = {"base_path": str(test_data_path)}

        assert DataProvider.validate_params(test_provider, test_params)
        assert not DataProvider.validate_params(test_provider, {"base_path_missplled": "test"})

        dp = DataProvider.get_data_provider(test_provider, test_params)
        assert isinstance(dp, SQLLiteProvider)
        assert dp._params == SQLLiteProviderParams.parse_obj(test_params)

        with pytest.raises(NotImplementedError) as err:
            DataProvider.validate_params("non_existent_provider", {"base_path_missplled": "test"})
        assert err.type == NotImplementedError

    def test_supported_providers(self):
        for provider in DataProvider.supported_providers.values():
            assert issubclass(provider, DataProvider)
            # Fail test if subcless is not imported here => probably not tested
            assert provider in globals().values()

    def test_unsupported_provider(self):
        with pytest.raises(NotImplementedError) as err:
            DataProvider.get_data_provider("non_existent_provider", {"base_path_missplled": "test"})
        assert err.type == NotImplementedError

    def test_get_connection(self, test_data_provider):
        mockuser_id = "123"
        mock_password = "password"
        mock_key = b"wrong key"
        assert isinstance(test_data_provider, SQLLiteProvider)

        # Encrypted

        # New user (no lock)

        with pytest.raises(ValueError) as err:
            conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key=mock_key)
        assert err.type == ValueError and err.value.args == (
            "No lock file for this user. A `str` type password must be provided",
        )

        conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key=mock_password)
        assert isinstance(conn, SQLLiteConnection)

        # Known user (lock file found)
        with pytest.raises(ValueError) as err:
            conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key=float(1))  # type:ignore
        assert err.type == ValueError and err.value.args == (
            "Lock file found. Either a `str` password ot `bytes` key must be provided",
        )

        conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key=mock_password)

        assert isinstance(conn, SQLLiteConnection)

        conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key=conn.key)

        assert isinstance(conn, SQLLiteConnection)

        key = conn.key
        lock = test_data_provider.get_lock(user_id=mockuser_id)
        assert lock
        base_path = test_data_provider._params.base_path / mockuser_id
        user_lock_path = base_path.joinpath("lock")
        user_lock_path.write_bytes(EncryptionProdiver(password_or_key=key, init_token=lock).encrypt(b"wrong_user_id"))

        with pytest.raises(DataCorruptionError) as err:
            conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key=key)
        assert err.type == DataCorruptionError and err.value.type == DataCorruptionType.INCORRECT_LOCK

        with pytest.raises(IncorrectPasswordKeyError) as err:
            conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key="wrong password")
        assert err.type == IncorrectPasswordKeyError

        # Test data corruption
        mockuser_id = "corrupt1"
        conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key=mock_password)

        # store config and drop lock
        conn.store_user_data(data="test config", category="config")
        test_data_provider._params.base_path.joinpath(mockuser_id, "lock").unlink()

        with pytest.raises(DataCorruptionError) as err:
            conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key=mock_password)
        assert err.type == DataCorruptionError and err.value.type == DataCorruptionType.USER_DATA_NO_LOCK

        mockuser_id = "corrupt2"
        conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key=mock_password)

        # store log and drop lock
        conn.append_log("poll", datetime.datetime.now(), "log")
        test_data_provider._params.base_path.joinpath(mockuser_id, "lock").unlink()

        with pytest.raises(DataCorruptionError) as err:
            conn = test_data_provider.get_connection(user_id=mockuser_id, password_or_key=mock_password)
        assert err.type == DataCorruptionError and err.value.type == DataCorruptionType.USER_DATA_NO_LOCK


class TestDataConnection:
    def test_abstract(self):
        with pytest.raises(TypeError, match=r"Can't instantiate abstract class.*"):
            DataConnection()  # type: ignore


class TestSQLLiteProvider:
    def test_provider(self, tmp_path_factory):
        assert SQLLiteProvider.name == "sqllite"

        mockuser_id = "123"

        assert not DataProvider.validate_params("sqllite", {"base_path_missplled": "test"})

        # Incorrect params
        with pytest.raises(ValidationError) as err:
            DataProvider.get_data_provider("sqllite", {"base_path_missplled": "test"})
        assert err.type == ValidationError

        # Correct params
        data_path: Path = tmp_path_factory.mktemp("data")
        provider = DataProvider.get_data_provider("sqllite", {"base_path": str(data_path)})

        assert isinstance(provider, SQLLiteProvider)
        assert provider.check_user_data_exist(user_id=mockuser_id) is False
        assert provider.check_user_data_exist(user_id=mockuser_id, category="config") is False
        assert provider.check_lock_exist(user_id=mockuser_id) is False
        assert provider.get_lock(user_id=mockuser_id) is None

        base_path = data_path / mockuser_id
        base_path.mkdir(parents=True, exist_ok=True)

        user_data_path = base_path.joinpath("data.db")
        user_data_path.touch()
        assert provider.check_user_data_exist(user_id=mockuser_id) is True

        user_lock_path = base_path.joinpath("lock")
        user_lock_path.touch()
        assert provider.check_lock_exist(user_id=mockuser_id) is True
        assert provider.get_lock(user_id=mockuser_id) == b""

        provider.save_lock(user_id=mockuser_id, lock=b"test lock")
        assert provider.get_lock(user_id=mockuser_id) == b"test lock"


class TestSQLLiteConnection:
    def test_config(self, mockuser, test_data_provider):
        assert isinstance(mockuser, User)
        assert isinstance(test_data_provider, SQLLiteProvider)
        mock_password = "password"

        conn = test_data_provider.get_connection(mockuser.id, mock_password)
        assert isinstance(conn, SQLLiteConnection)

        config = mockuser.json(exclude_unset=True, ensure_ascii=False)

        assert conn.store_user_data(data=config, category="config")

        # Test data is encrypted at rest
        engine = sa.create_engine(
            test_data_provider.BASE_URI
            + str(test_data_provider._params.base_path.joinpath(mockuser.id, test_data_provider.DB_FILE_NAME))
        )

        with engine.connect() as econn:
            result = econn.execute(
                sa.text(f"SELECT data FROM {test_data_provider.USER_DATA_TABLE} WHERE category='config'")
            )
            config_data_encrypted = result.scalar()

        # Validate data was encrypted
        assert config_data_encrypted.decode() != config

        # Check correct loading of the config back
        assert conn.get_user_data(category="config") == config

    def test_connection(self, mockuser, test_data_provider):
        assert isinstance(mockuser, User)
        assert isinstance(test_data_provider, SQLLiteProvider)
        mock_password = "password"

        conn = test_data_provider.get_connection(mockuser.id, mock_password)
        assert isinstance(conn, SQLLiteConnection)

        poll_code_1 = "poll1"
        poll_code_2 = "poll2"
        row_data_base = "some"
        now = datetime.datetime.now()

        poll_1_values = []
        poll_1_poll_tss = []
        for i in range(1, 10):
            poll_1_values.append(row_data_base + str(i))
            poll_1_poll_tss.append(now - datetime.timedelta(days=i - 1))
            id = conn.append_log(poll_code_1, now - datetime.timedelta(days=i - 1), row_data_base + str(i))
            assert id == i

        poll_2_values = []
        poll_2_poll_tss = []
        for i in range(10, 20):
            poll_2_values.append(row_data_base + str(i))
            poll_2_poll_tss.append(now - datetime.timedelta(days=i - 10))
            id = conn.append_log(poll_code_2, now - datetime.timedelta(days=i - 10), row_data_base + str(i))
            assert id == i

        # Test data is encrypted at rest
        engine = sa.create_engine(
            test_data_provider.BASE_URI
            + str(test_data_provider._params.base_path.joinpath(mockuser.id, test_data_provider.DB_FILE_NAME))
        )

        meta = sa.MetaData()

        data_table = sa.Table(
            test_data_provider.POLL_LOG_TABLE,
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
        assert set(map(lambda x: x[2], all_logs)) == set(poll_1_values + poll_2_values)

        # Check get_last_n_logs
        test_logs = conn.get_last_n_logs("unknown_poll", 1)
        assert len(test_logs) == 0

        test_logs = conn.get_last_n_logs(poll_code_1, 1)
        assert len(test_logs) == 1
        test_id, test_poll_ts, test_log = test_logs[0]

        # Check get_logs
        assert conn.get_log(test_id) == (test_id, now, poll_1_values[0])

        # Check get_logs
        test_logs = conn.get_last_n_logs(poll_code_1, 5)
        assert len(test_logs) == 5

        test_ids = list(map(lambda x: x[0], test_logs))

        assert conn.get_logs(test_ids) == list(zip(test_ids, poll_1_poll_tss, poll_1_values))

        # Check get_last_logs
        test_logs = conn.get_last_logs(
            poll_code_1,
            date_from=datetime.datetime.now() - datetime.timedelta(days=3),
            max_rows=3,
        )
        assert len(test_logs) == 3

        test_logs = conn.get_last_logs(
            poll_code_1,
            date_from=datetime.datetime.now() - datetime.timedelta(days=1),
            max_rows=3,
        )
        assert len(test_logs) == 1

        test_ids = list(map(lambda x: x[0], test_logs))

        assert conn.get_logs(test_ids) == list(zip(test_ids, poll_1_poll_tss, poll_1_values))

        # Check get_poll_logs
        test_logs = conn.get_poll_logs(
            poll_code_1,
            date_to=datetime.datetime.now() - datetime.timedelta(days=10),
            max_rows=3,
        )
        assert len(test_logs) == 0

        test_logs = conn.get_poll_logs(
            poll_code_1,
            date_to=datetime.datetime.now() - datetime.timedelta(days=8),
            max_rows=3,
        )
        assert len(test_logs) == 1

        # Check update_log
        test_id, test_poll_ts, test_log = conn.get_last_n_logs(poll_code_1, 1)[0]
        conn.update_log(test_id, log="new data")
        assert conn.get_log(test_id)[2] == "new data"
        assert conn.get_log(test_id)[1] == test_poll_ts
        conn.update_log(test_id, poll_ts=test_poll_ts - datetime.timedelta(days=10))
        assert conn.get_log(test_id)[2] == "new data"
        assert conn.get_log(test_id)[1] == test_poll_ts - datetime.timedelta(days=10)

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
