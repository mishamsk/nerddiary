from __future__ import annotations

import datetime
import enum
from abc import ABC, abstractmethod
from pathlib import Path

import sqlalchemy as sa
from cryptography.fernet import InvalidToken
from pydantic import BaseModel, DirectoryPath, PrivateAttr, ValidationError
from sqlalchemy.dialects.sqlite import BLOB
from sqlalchemy.sql.expression import Select

from .crypto import EncryptionProdiver

from typing import Any, ClassVar, Dict, List, Tuple, Type


class DataCorruptionType(enum.Enum):
    UNDEFINED = enum.auto()
    LOCK_WRITE_FAILURE = enum.auto()
    INCORRECT_LOCK = enum.auto()
    CONFIG_NO_LOCK = enum.auto()
    DATA_NO_LOCK = enum.auto()


class DataCorruptionError(Exception):  # pragma: no cover
    def __init__(self, type: DataCorruptionType = DataCorruptionType.UNDEFINED) -> None:
        self.type = type
        super().__init__(type)

    def __str__(self) -> str:
        mes = ""
        match self.type:
            case DataCorruptionType.INCORRECT_LOCK:
                mes = "Lock file didn't match this user_id"
            case DataCorruptionType.LOCK_WRITE_FAILURE:
                mes = "Failed to create lock file"
            case DataCorruptionType.CONFIG_NO_LOCK:
                mes = "Config exists, but lock file is missing"
            case DataCorruptionType.DATA_NO_LOCK:
                mes = "Data exists, but lock file is missing"
            case _:
                mes = "Unspecified data corruption"

        return f"Data corrupted: {mes}"


class IncorrectPasswordKeyError(Exception):
    pass


class DataProvider(ABC):
    name: ClassVar[str]

    def __init__(self, params: Dict[str, Any] | None) -> None:
        super().__init__()

    @classmethod
    @property
    def supported_providers(cls) -> Dict[str, Type[DataProvider]]:
        def all_subclasses(cls) -> Dict[str, Type[DataProvider]]:
            subc = {} | {cl.name: cl for cl in cls.__subclasses__()}

            sub_subc = {}
            for c in subc.values():
                sub_subc |= all_subclasses(c)

            return subc | sub_subc

        return all_subclasses(cls)

    def get_connection(self, user_id: str, password_or_key: str | bytes) -> DataConnection:
        """Creates a data connection for a new or existing user. Checks for correct password/key and data corruption.

        If this is a new user (meaning `check_lock_exist()` returns False) a `str` password must be provided. If a lock file exist, either a password or encryption `key` may be provided (see `DataConnection` property `key`).

        Throws `DataCorruptionError` with the corresponding `DataCorruptionType` if config or data exist but lock file is missing (data corruption), or if lock file corrupted or couldn't be created for any reason.

        Throws `IncorrectPasswordKeyError` if incorrect password or key was provided. Also throws
        """
        encr = None

        if not self.check_lock_exist(user_id):
            if self.check_config_exist(user_id):
                raise DataCorruptionError(DataCorruptionType.CONFIG_NO_LOCK)

            if self.check_data_exist(user_id):
                raise DataCorruptionError(DataCorruptionType.DATA_NO_LOCK)

            if not isinstance(password_or_key, str):
                raise ValueError("No lock file for this user. A `str` type password must be provided")

            encr = EncryptionProdiver(password_or_key)
            lock = encr.encrypt(user_id.encode())
            if not self.save_lock(user_id, lock):
                raise DataCorruptionError(DataCorruptionType.LOCK_WRITE_FAILURE)  # pragma: no cover
        else:
            if not isinstance(password_or_key, str) and not isinstance(password_or_key, bytes):
                raise ValueError("Lock file found. Either a `str` password ot `bytes` key must be provided")

            lock = self.get_lock(user_id)
            try:
                encr = EncryptionProdiver(password_or_key, init_token=lock, control_message=user_id.encode())
            except InvalidToken:
                raise IncorrectPasswordKeyError()
            except ValueError:
                raise DataCorruptionError(DataCorruptionType.INCORRECT_LOCK)

        return self._get_connection(user_id, encr)

    @abstractmethod
    def _get_connection(self, user_id: str, encr: EncryptionProdiver) -> DataConnection:
        pass  # pragma: no cover

    @abstractmethod
    def check_data_exist(self, user_id: str) -> bool:
        pass  # pragma: no cover

    @abstractmethod
    def check_config_exist(self, user_id: str) -> bool:
        pass  # pragma: no cover

    @abstractmethod
    def check_lock_exist(self, user_id: str) -> bool:
        pass  # pragma: no cover

    @abstractmethod
    def get_lock(self, user_id: str) -> bytes | None:
        pass  # pragma: no cover

    @abstractmethod
    def save_lock(self, user_id: str, lock: bytes) -> bool:
        pass  # pragma: no cover

    @classmethod
    @abstractmethod
    def _validate_params(cls, params: Dict[str, Any] | None) -> bool:
        pass  # pragma: no cover

    @classmethod
    def validate_params(cls, name: str, params: Dict[str, Any] | None) -> bool:

        if name not in cls.supported_providers:
            raise NotImplementedError(f"Data provider {name} doesn't exist")

        return cls.supported_providers[name]._validate_params(params)

    @classmethod
    def get_data_provider(cls, name: str, params: Dict[str, Any] | None) -> DataProvider:

        if name not in cls.supported_providers:
            raise NotImplementedError(f"Data provider {name} doesn't exist")

        return cls.supported_providers[name](params)


class DataConnection(ABC):
    def __init__(
        self,
        data_provider: DataProvider,
        user_id: str,
        encryption_provider: EncryptionProdiver | None,
    ) -> None:
        super().__init__()

        self._data_provider = data_provider
        self._user_id = user_id
        self._encryption_provider = encryption_provider

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def key(self) -> bytes:
        return self._encryption_provider.key

    @abstractmethod
    def store_config(self, config: str) -> bool:
        """Saves serialized config"""
        pass  # pragma: no cover

    @abstractmethod
    def load_config(self) -> str | None:
        """Reads serialized config if exists"""
        pass  # pragma: no cover

    @abstractmethod
    def append_log(self, poll_code: str, log: str) -> bool:
        """Appends a single serialized `log` for a given `poll_code`"""
        pass  # pragma: no cover

    def update_log(self, id: Any, log: str) -> bool:
        """Updates a log identified by `id` with a new serialized `log`"""
        raise NotImplementedError("This provider doesn't support row updates")  # pragma: no cover

    def get_all_logs(self) -> List[Tuple[Any, str]]:
        """Get all serialized logs"""
        raise NotImplementedError("This provider doesn't support row updates")  # pragma: no cover

    def get_log(self, id: Any) -> Tuple[Any, str]:
        """Get a single serialized log identified by `id`"""
        ret = self.get_logs([id])
        if len(ret) == 1:
            return ret[0]
        else:
            raise ValueError("Log id wasn't found")

    def get_logs(
        self,
        ids: List[Any],
    ) -> List[Tuple[Any, str]]:
        """Get a list of serialized logs identified by `ids`"""
        raise NotImplementedError("This provider doesn't support retrieving rows")  # pragma: no cover

    def get_poll_logs(
        self,
        poll_code: str,
        date_from: datetime.datetime = None,
        date_to: datetime.datetime = None,
        max_rows: int = None,
    ) -> List[Tuple[Any, str]]:
        """Get a list of serialized logs for a given `poll_code` sorted by creation date, optionally filtered by `date_from`, `date_to` and optionally limited to `max_rows`"""
        raise NotImplementedError("This provider doesn't support retrieving rows")  # pragma: no cover

    def get_last_n_logs(self, poll_code: str, count: int) -> List[Tuple[Any, str]]:
        return self.get_poll_logs(poll_code, max_rows=count)

    def get_last_logs(self, poll_code: str, date_from: datetime.datetime, max_rows: int) -> List[Tuple[Any, str]]:
        return self.get_poll_logs(poll_code, date_from=date_from, max_rows=max_rows)


class SQLLiteProviderParams(BaseModel):
    base_path: DirectoryPath
    _base_uri: str = PrivateAttr(default="sqlite:///")

    class Config:
        extra = "forbid"


class SQLLiteProvider(DataProvider):
    name = "sqllite"

    def __init__(self, params: Dict[str, Any]) -> None:
        super().__init__(params)

        self._params = SQLLiteProviderParams.parse_obj(params)

    def _get_connection(self, user_id: str, encr: EncryptionProdiver) -> SQLLiteConnection:
        return SQLLiteConnection(self, user_id, encr)

    def check_data_exist(self, user_id: str) -> bool:
        data_path = self._params.base_path.joinpath(user_id, "data.db")
        return data_path.exists() and data_path.is_file()

    def check_config_exist(self, user_id: str) -> bool:
        config_path = self._params.base_path.joinpath(user_id, "config")
        return config_path.exists() and config_path.is_file()

    def check_lock_exist(self, user_id: str) -> bool:
        lock_path = self._params.base_path.joinpath(user_id, "lock")
        return lock_path.exists() and lock_path.is_file()

    def get_lock(self, user_id: str) -> bytes | None:

        if not self.check_lock_exist(user_id):
            return None

        lock_path = self._params.base_path.joinpath(user_id, "lock")
        return lock_path.read_bytes()

    def save_lock(self, user_id: str, lock: bytes) -> bool:
        assert isinstance(self._params.base_path, Path)

        self._params.base_path.joinpath(user_id).mkdir(parents=True, exist_ok=True)
        lock_path = self._params.base_path.joinpath(user_id, "lock")

        try:
            lock_path.write_bytes(lock)
        except OSError:  # pragma: no cover
            return False

        return True

    @classmethod
    def _validate_params(cls, params: Dict[str, Any] | None) -> bool:
        try:
            SQLLiteProviderParams.parse_obj(params)
        except ValidationError:
            return False

        return True


class SQLLiteConnection(DataConnection):
    def __init__(
        self,
        data_provider: SQLLiteProvider,
        user_id: str,
        encryption_provider: EncryptionProdiver = None,
    ) -> None:
        super().__init__(data_provider, user_id, encryption_provider)

        base_path = data_provider._params.base_path
        base_path.joinpath(self.user_id).mkdir(exist_ok=True)

        self._engine = engine = sa.create_engine(
            data_provider._params._base_uri + str(data_provider._params.base_path.joinpath(self.user_id, "data.db"))
        )

        self._meta = meta = sa.MetaData()

        self._data_table = data_table = sa.Table(
            "data",
            meta,
            sa.Column("id", sa.Integer, primary_key=True, index=True, nullable=False),
            sa.Column("poll_code", sa.String, index=True, unique=False, nullable=False),
            sa.Column("log", BLOB, nullable=False),
            sa.Column("created_ts", sa.DATETIME, nullable=False),
            sa.Column("updated_ts", sa.DATETIME, nullable=False),
        )

        with engine.connect() as conn:
            data_table.create(conn, checkfirst=True)

    def store_config(self, config: str) -> bool:
        assert isinstance(self._data_provider, SQLLiteProvider)

        config_path = self._data_provider._params.base_path.joinpath(self.user_id, "config")

        assert isinstance(config_path, Path)

        try:
            config_path.write_bytes(self._encryption_provider.encrypt(config.encode()))
        except OSError:  # pragma: no cover
            return False

        return True

    def load_config(self) -> str | None:
        assert isinstance(self._data_provider, SQLLiteProvider)

        config_path = self._data_provider._params.base_path.joinpath(self.user_id, "config")

        assert isinstance(config_path, Path)

        if not config_path.exists():
            return None
        else:
            return self._encryption_provider.decrypt(config_path.read_bytes()).decode()

    def append_log(self, poll_code: str, log: str) -> int | None:
        now = datetime.datetime.now()

        log_out = self._encryption_provider.encrypt(log.encode())

        stmt = self._data_table.insert(
            values={
                "log": log_out,
                "poll_code": poll_code,
                "created_ts": now,
                "updated_ts": now,
            }
        )

        with self._engine.connect() as conn:
            result = conn.execute(stmt)

            if result.rowcount == 1:
                return result.inserted_primary_key[0]
            else:
                return None

    def _query_and_decrypt(self, stmt: Select) -> List[Tuple[Any, str]]:
        ret = []
        with self._engine.connect() as conn:
            result = conn.execute(stmt)

            rows = result.all()
            for row in rows:
                ret.append(
                    (
                        row.id,
                        self._encryption_provider.decrypt(row.log).decode(),
                    )
                )

        return ret

    def get_logs(
        self,
        ids: List[Any],
    ) -> List[Tuple[Any, str]]:
        stmt = self._data_table.select().where(self._data_table.c.id.in_(ids))

        return self._query_and_decrypt(stmt)

    def update_log(self, id: Any, log: str) -> bool:
        now = datetime.datetime.now()

        log_out = self._encryption_provider.encrypt(log.encode())

        stmt = self._data_table.update().where(self._data_table.c.id == id).values(log=log_out, updated_ts=now)

        with self._engine.connect() as conn:
            result = conn.execute(stmt)

            if result.rowcount == 1:
                return True
            else:
                return False

    def get_all_logs(self) -> List[Tuple[Any, str]]:
        stmt = self._data_table.select()

        return self._query_and_decrypt(stmt)

    def get_poll_logs(
        self,
        poll_code: str,
        date_from: datetime.datetime = None,
        date_to: datetime.datetime = None,
        max_rows: int = None,
    ) -> List[Tuple[Any, str]]:
        stmt = self._data_table.select().where(self._data_table.c.poll_code == poll_code)

        if date_from:
            stmt = stmt.where(self._data_table.c.created_ts >= date_from)

        if date_to:
            stmt = stmt.where(self._data_table.c.created_ts <= date_to)

        if max_rows:
            stmt = stmt.limit(max_rows)

        return self._query_and_decrypt(stmt)
