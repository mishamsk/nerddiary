from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..data.data import DataProvider
from .config import NerdDiaryConfig

# import typing as t

logger = logging.getLogger(__name__)


class NerdDiary:
    def __init__(self, session: str = "default", config: NerdDiaryConfig = NerdDiaryConfig()) -> None:
        self.config = config
        self._running = False
        self._stop = None
        self._data_provider = DataProvider.get_data_provider(config.data_provider_name, config.data_provider_params)
        self._scheduler = AsyncIOScheduler()

    async def start(self):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("Start the loop before starting NerdDiary client")

        self._stop = asyncio.Future()

        self._scheduler.start()
        self._running = True

    async def close(self):
        # Remove all jobs and shutdown the scheduler
        self._scheduler.remove_all_jobs()
        self._scheduler.shutdown()

    def stop(self):
        self._running = False
        if not self._stop.done():
            self._stop.set_result("stopped")

    async def __aenter__(self):
        loop = asyncio.get_event_loop()
        if loop.is_running():
            await self.start()
        else:
            pass

    async def __aexit__(self, *exc_info):
        logger.error("Exception caught before client was closed", exc_info=exc_info)
        await self.close()

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
