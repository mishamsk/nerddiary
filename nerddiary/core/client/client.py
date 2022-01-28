from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import NerdDiaryConfig

# import typing as t

logger = logging.getLogger(__name__)


class NerdDiary:
    def __init__(self, config: NerdDiaryConfig = NerdDiaryConfig()) -> None:
        self.config = config
        self._running = False
        self._stop = None
        self._scheduler = AsyncIOScheduler()

    async def start(self):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("Start the loop before creating an instance of NerdDiary class")

        self._stop = asyncio.Future()

        self._scheduler.start()
        self._scheduler.add_job(self._test_job, "interval", seconds=1)
        self._running = True
        self._main_loop_task = asyncio.create_task(self._main_loop())
        result = await self._stop
        await self._clean_up(result)

    async def _main_loop(self):
        try:
            while self._running:
                print("We are live in the loop!")
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass
        finally:
            # Serialize
            pass

    async def _test_job(self):
        print("We are live in the job!")

    async def _clean_up(self, result: str):
        # Remove all jobs and shutdown the scheduler
        self._scheduler.remove_all_jobs()
        self._scheduler.shutdown()

        self._main_loop_task.cancel()

    def stop(self):
        self._running = False
        if not self._stop.done():
            self._stop.set_result("stopped")
