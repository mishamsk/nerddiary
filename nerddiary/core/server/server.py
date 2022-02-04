from __future__ import annotations

import asyncio
import logging

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..data.data import DataProvider
from .config import NerdDiaryConfig
from .job import Job
from .session.session import SessionSpawner, UserSession
from .session.string import StringSessionSpawner

from typing import Callable, Coroutine, Dict, Type

# import typing as t

logger = logging.getLogger(__name__)


class NerdDiary:
    def __init__(self, session: str | SessionSpawner = "default", config: NerdDiaryConfig = NerdDiaryConfig()) -> None:
        self._config = config

        self._data_provider = DataProvider.get_data_provider(config.data_provider_name, config.data_provider_params)

        self._scheduler = AsyncIOScheduler(jobstores={"default": SQLAlchemyJobStore(url=config.jobstore_sa_url)})

        self._job_queue = asyncio.Queue()

        if isinstance(session, str):
            self._session_spawner = StringSessionSpawner(
                params=config.session_spawner_params,
                data_provider=self._data_provider,
                scheduler=self._scheduler,
                job_queue=self._job_queue,
            )
        else:
            self._session_spawner = session

        self._sessions: Dict[str, UserSession]

        self._running = False
        self._job_dispatcher = None
        self._job_subscribers: Dict[Type[Job], Callable[[Job], Coroutine[None, None, bool]]] = {}

    @property
    def session(self) -> SessionSpawner:
        return self._session_spawner

    async def start(self):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("Start the loop before starting NerdDiary client")

        self._job_dispatcher = asyncio.create_task(self._dispatch_job())

        self._scheduler.start()
        self._running = True

    async def _dispatch_job(self):
        while self._running:
            # Wait for subscribers
            if len(self._job_subscribers):
                await asyncio.sleep(1)

            job = await self._job_queue.get()

            res = False
            for type, callback in self._job_subscribers.items():
                # Dispatch only if job type matches subscribed type
                if not isinstance(job, type):
                    continue

                try:
                    res = await callback(job)
                except Exception as exc:
                    logger.warning(
                        f"Exception while processing job <{job}> with callback <{callback.__module__}.{callback.__name__}>",
                        exc_info=exc,
                    )

                if res:
                    self._job_queue.task_done()
                    break

            if not res:
                logger.warning(f"Job <{job}> failed to process by any of the subscribers. Skipping")
                self._job_queue.task_done()

            await asyncio.sleep(0.1)

    async def close(self):
        if self._running:
            # Stop any internal loops
            self.stop()

        # If job dispatcher exist, wait for it to stop
        if self._job_dispatcher:
            await self._job_dispatcher

        # Remove all jobs and shutdown the scheduler
        self._scheduler.remove_all_jobs()
        self._scheduler.shutdown()
        for ses in self._sessions.values():
            await ses.close()

    def stop(self):
        self._scheduler.pause()
        self._running = False

    async def __aenter__(self):
        loop = asyncio.get_event_loop()
        if loop.is_running():
            await self.start()
        else:
            loop.run_until_complete(self.start())

    async def __aexit__(self, *exc_info):
        logger.error("Exception caught before client was closed", exc_info=exc_info)

        loop = asyncio.get_event_loop()
        if loop.is_running():
            await self.close()
        else:
            loop.run_until_complete(self.close())

    # @classmethod
    # def from_file(
    #     cls,
    #     id: int,
    #     config_file_path: str,
    #     default_timezone: TimeZone,
    # ) -> User:

    #     logger.debug(f"Reading user config file at: {config_file_path}")

    #     # Adding chat_id to config
    #     config = {"id": id, "config_file_path": config_file_path}

    #     try:
    #         with open(config_file_path) as json_data_file:
    #             config |= json.load(json_data_file)
    #     except OSError:
    #         logger.error(f"File at '{config_file_path}' doesn't exist or can't be open")

    #         raise ValueError(f"File at '{config_file_path}' doesn't exist or can't be open")

    #     # If timezone not set, use the default one
    #     if config.get("timezone", None) is None:
    #         config["timezone"] = default_timezone.tzname

    #     # If question types passed, add them
    #     # if ext_question_types:
    #     #     if not config.get("question_types", None):
    #     #         config["question_types"] = {}

    #     #     config["question_types"] |= ext_question_types

    #     return cls.parse_obj(config)

    # @classmethod
    # def from_folder(
    #     cls,
    #     folder: str,
    #     default_timezone: TimeZone,
    # ) -> Dict[int, User]:
    #     config_files = glob(f"{folder}/user_conf_*.json")

    #     ret = {}

    #     for config_file_path in config_files:
    #         id = int(config_file_path.split("_")[2][:-5])
    #         ret[id] = User.from_file(
    #             id,
    #             config_file_path,
    #             default_timezone,
    #         )

    #     return ret
