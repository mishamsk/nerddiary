from __future__ import annotations

import datetime
import enum
from abc import ABC, abstractmethod
from pathlib import Path

import arrow
import sqlalchemy as sa
from cryptography.fernet import InvalidToken
from pydantic import BaseModel, DirectoryPath, ValidationError
from sqlalchemy.dialects.sqlite import BLOB
from sqlalchemy.sql.expression import Select

from .crypto import EncryptionProdiver

from typing import Any, ClassVar, Dict, List, Tuple, Type


class DataCorruptionType(enum.Enum):
    UNDEFINED = enum.auto()
    LOCK_WRITE_FAILURE = enum.auto()
    INCORRECT_LOCK = enum.auto()
    USER_DATA_NO_LOCK = enum.auto()


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
            case DataCorruptionType.USER_DATA_NO_LOCK:
                mes = "User data exists, but lock file is missing"
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
            if self.check_user_data_exist(user_id):
                raise DataCorruptionError(DataCorruptionType.USER_DATA_NO_LOCK)

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
            assert lock

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
    def get_user_list(self) -> List[str]:
        pass

    @abstractmethod
    def check_user_data_exist(self, user_id: str, category: str | None = None) -> bool:
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
        encryption_provider: EncryptionProdiver,
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
    def store_user_data(self, data: str, category: str) -> bool:
        """Saves serialized config"""
        pass  # pragma: no cover

    @abstractmethod
    def get_user_data(self, category: str) -> str | None:
        """Reads serialized config if exists"""
        pass  # pragma: no cover

    @abstractmethod
    def append_log(self, poll_code: str, poll_ts: datetime.datetime, log: str) -> bool:
        """Appends a single serialized `log` for a given `poll_code`

        Args:
            poll_code (str): poll code
            poll_ts (datetime.datetime): poll timestamp - the date to which this log belongs
            log (str): seriazlized poll answers (log)

        Returns:
            bool: 'True' if append was succesful
        """
        pass  # pragma: no cover

    def update_log(self, id: int, poll_ts: datetime.datetime | None = None, log: str | None = None) -> bool:
        """Updates a log identified by `id` with a new serialized `log`"""
        raise NotImplementedError("This provider doesn't support row updates")  # pragma: no cover

    def get_all_logs(self) -> List[Tuple[int, str, datetime.datetime, str]]:
        """Get all serialized logs"""
        return self.get_poll_logs()

    def get_log(self, id: int) -> Tuple[int, str, datetime.datetime, str]:
        """Get a single serialized log identified by `id`"""
        ret = self.get_logs([id])
        if len(ret) == 1:
            return ret[0]
        else:
            raise ValueError("Log id wasn't found")

    def get_logs(
        self,
        ids: List[int],
    ) -> List[Tuple[int, str, datetime.datetime, str]]:
        """Get a list of serialized logs identified by `ids`"""
        raise NotImplementedError("This provider doesn't support retrieving rows")  # pragma: no cover

    def get_poll_logs(
        self,
        poll_code: str | None = None,
        date_from: datetime.datetime | None = None,
        date_to: datetime.datetime | None = None,
        max_rows: int | None = None,
        skip: int | None = None,
    ) -> List[Tuple[int, str, datetime.datetime, str]]:
        """Get a list of serialized logs for a given `poll_code` sorted by creation date, optionally filtered by `date_from`, `date_to` and optionally limited to `max_rows`+`skip` starting from `skip` (ordered by date DESC)"""
        raise NotImplementedError("This provider doesn't support retrieving rows")  # pragma: no cover

    def get_last_n_logs(
        self,
        count: int,
        *,
        poll_code: str | None = None,
        skip: int | None = None,
    ) -> List[Tuple[int, str, datetime.datetime, str]]:
        return self.get_poll_logs(poll_code=poll_code, max_rows=count, skip=skip)


class SQLLiteProviderParams(BaseModel):
    base_path: DirectoryPath

    class Config:
        extra = "forbid"


class SQLLiteProvider(DataProvider):
    name = "sqllite"
    BASE_URI = "sqlite:///"
    DB_FILE_NAME = "data.db"
    POLL_LOG_TABLE = "poll_log"
    USER_DATA_TABLE = "user_data"

    def __init__(self, params: Dict[str, Any]) -> None:
        super().__init__(params)

        self._params = SQLLiteProviderParams.parse_obj(params)

    def _get_connection(self, user_id: str, encr: EncryptionProdiver) -> SQLLiteConnection:
        return SQLLiteConnection(self, user_id, encr)

    def get_user_list(self) -> List[str]:
        ret = []

        for file in self._params.base_path.iterdir():
            if file.is_dir():
                ret.append(str(file.name))

        return ret

    def check_user_data_exist(self, user_id: str, category: str | None = None) -> bool:
        data_path = self._params.base_path.joinpath(user_id, self.DB_FILE_NAME)
        db_exists = data_path.exists() and data_path.is_file()

        if category is None or not db_exists:
            return db_exists

        # TODO: check user id is a valid folder path
        engine = sa.create_engine(self.BASE_URI + str(self._params.base_path.joinpath(user_id, self.DB_FILE_NAME)))

        with engine.connect() as conn:
            result = conn.execute(sa.text(f"SELECT count(*) FROM {self.USER_DATA_TABLE} WHERE category='{category}'"))
            count = result.scalar()
            if count == 1:
                return True
            else:
                return False

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
        encryption_provider: EncryptionProdiver,
    ) -> None:
        super().__init__(data_provider, user_id, encryption_provider)

        base_path = data_provider._params.base_path
        base_path.joinpath(self.user_id).mkdir(exist_ok=True)

        # TODO: check user id is a valid folder path
        self._engine = engine = sa.create_engine(
            data_provider.BASE_URI
            + str(data_provider._params.base_path.joinpath(self.user_id, data_provider.DB_FILE_NAME))
        )

        self._meta = meta = sa.MetaData()

        self._poll_log_table = poll_log_table = sa.Table(
            data_provider.POLL_LOG_TABLE,
            meta,
            sa.Column("id", sa.Integer, primary_key=True, index=True, nullable=False),
            sa.Column("poll_code", sa.String, index=True, unique=False, nullable=False),
            sa.Column("poll_ts", sa.TIMESTAMP(timezone=True), index=True, unique=False, nullable=False),
            sa.Column("log", BLOB, nullable=False),
            sa.Column("created_ts", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_ts", sa.TIMESTAMP(timezone=True), nullable=False),
        )

        self._user_data_table = user_data_table = sa.Table(
            data_provider.USER_DATA_TABLE,
            meta,
            sa.Column("category", sa.String, primary_key=True, index=True, unique=True, nullable=False),
            sa.Column("data", BLOB, nullable=False),
            sa.Column("created_ts", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_ts", sa.TIMESTAMP(timezone=True), nullable=False),
        )

        with engine.connect() as conn:
            poll_log_table.create(conn, checkfirst=True)
            user_data_table.create(conn, checkfirst=True)

    def store_user_data(self, data: str, category: str) -> bool:
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        stmt = self._user_data_table.select().where(self._user_data_table.c.category == category)
        new = True
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()

            if row:
                new = False

        stmt = None

        data_out = self._encryption_provider.encrypt(data.encode())

        if new:
            stmt = self._user_data_table.insert(
                values={
                    "data": data_out,
                    "category": category,
                    "created_ts": now,
                    "updated_ts": now,
                }
            )
        else:
            stmt = self._user_data_table.update(
                values={
                    "data": data_out,
                    "category": category,
                    "created_ts": now,
                    "updated_ts": now,
                }
            ).where(self._user_data_table.c.category == category)

        with self._engine.connect() as conn:
            result = conn.execute(stmt)

            if result.rowcount == 1:
                return True
            else:
                return False

    def get_user_data(self, category: str) -> str | None:
        stmt = sa.select(self._user_data_table.c.data).where(self._user_data_table.c.category == category)  # type: ignore

        with self._engine.connect() as conn:
            result = conn.execute(stmt)
            data = result.scalar()

            if data:
                return self._encryption_provider.decrypt(data).decode()
            else:
                return None

    def append_log(self, poll_code: str, poll_ts: datetime.datetime, log: str) -> int | None:
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        log_out = self._encryption_provider.encrypt(log.encode())

        stmt = self._poll_log_table.insert(
            values={
                "log": log_out,
                "poll_code": poll_code,
                "poll_ts": arrow.get(poll_ts).to("utc").datetime,
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

    def _query_and_decrypt(self, stmt: Select) -> List[Tuple[int, str, datetime.datetime, str]]:
        ret = []
        with self._engine.connect() as conn:
            result = conn.execute(stmt)

            rows = result.all()
            for row in rows:
                ret.append(
                    (
                        row["id"],
                        row["poll_code"],
                        row["poll_ts"],
                        self._encryption_provider.decrypt(row["log"]).decode(),
                    )
                )

        return ret

    def get_logs(
        self,
        ids: List[int],
    ) -> List[Tuple[int, str, datetime.datetime, str]]:
        stmt = self._poll_log_table.select().where(self._poll_log_table.c.id.in_(ids))

        return self._query_and_decrypt(stmt)

    def update_log(self, id: Any, poll_ts: datetime.datetime | None = None, log: str | None = None) -> bool:
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        stmt = self._poll_log_table.update().where(self._poll_log_table.c.id == id).values(updated_ts=now)
        if log is not None:
            log_out = self._encryption_provider.encrypt(log.encode())
            stmt = stmt.values(log=log_out)
        if poll_ts is not None:
            stmt = stmt.values(poll_ts=arrow.get(poll_ts).to("utc").datetime)

        with self._engine.connect() as conn:
            result = conn.execute(stmt)

            if result.rowcount == 1:
                return True
            else:
                return False

    def get_poll_logs(
        self,
        poll_code: str | None = None,
        date_from: datetime.datetime | None = None,
        date_to: datetime.datetime | None = None,
        max_rows: int | None = None,
        skip: int | None = None,
    ) -> List[Tuple[int, str, datetime.datetime, str]]:
        if not skip:
            skip = 0

        stmt = self._poll_log_table.select()

        if poll_code:
            stmt = stmt.where(self._poll_log_table.c.poll_code == poll_code)

        if date_from:
            stmt = stmt.where(self._poll_log_table.c.poll_ts >= arrow.get(date_from).to("utc").datetime)

        if date_to:
            stmt = stmt.where(self._poll_log_table.c.poll_ts <= arrow.get(date_to).to("utc").datetime)

        if max_rows:
            stmt = stmt.limit(max_rows + skip)

        stmt = stmt.order_by(self._poll_log_table.c.poll_ts.desc())

        return self._query_and_decrypt(stmt)[skip:]
