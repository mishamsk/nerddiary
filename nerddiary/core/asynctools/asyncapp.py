from __future__ import annotations

import abc
import asyncio
import logging
import signal
from time import sleep

from typing import Any, Awaitable, TypeVar

# from .delayedsignal import DelayedKeyboardInterrupt


_T = TypeVar("_T")
_A = TypeVar("_A", bound="AsyncApplication")


class AsyncApplication(abc.ABC):
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop = None,
        logger: logging.Logger = None,
    ):
        self._loop: asyncio.AbstractEventLoop | None = loop
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._loop_started_by_self = False
        self._closed = True

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop and not self._loop.is_closed():
            return self._loop

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            self._loop_started_by_self = True

        return self._loop

    @property
    def closed(self) -> bool:
        return self._closed

    def run(self) -> Any:
        res = None

        try:
            self._logger.debug("Executing app startup sequence")
            if self.start() is not None:
                self._logger.debug("Running the app")
                res = self._run_coro(self._arun())
        except BaseException as e:
            self._logger.error("Unhandled exception while running the app.\n" + str(e))
        finally:
            self._logger.debug("Closing the app")
            self.close()

        return res

    @abc.abstractmethod
    async def _astart(self):
        pass

    @abc.abstractmethod
    async def _aclose(self) -> bool:
        pass

    async def _arun(self) -> Any:
        raise NotImplementedError()

    async def astart(self: _A) -> _A:
        self._logger.debug(
            "Running <_astart> method, ensuring <aclose> is executed if SIGINT is sent before <_astart> is finished"
        )

        func_task: asyncio.Task | None = None
        hit_sigint = False

        def __handler(sig, frame):
            nonlocal hit_sigint
            hit_sigint = True

            self._logger.debug("SIGINT received while runnning <_astart>; cancelling immediately")
            if func_task:
                func_task.cancel()

        old_sigint_handler = None

        try:
            self._logger.debug("astart: Replacing SIGINT handler")
            old_sigint_handler = signal.signal(signal.SIGINT, __handler)

            func_task = self.loop.create_task(self._astart())

            # Set this even before start, in case start was interuppted but some cleaning is still necessary. Close method must be clever enough to check that object to be cleaned exist
            self._closed = False

            await func_task
        except asyncio.CancelledError:
            if hit_sigint:
                self._logger.warn("Closing app after SIGINT")
            else:
                self._logger.warn("<_astart> was cancelled. Closing app")

            res = await self.aclose()

            if hit_sigint:
                self._logger.debug("astart: Restoring SIGINT handler and re-rasing SIGINT")
                signal.signal(signal.SIGINT, old_sigint_handler)
                raise KeyboardInterrupt()

            if not res:
                raise
        finally:
            if not hit_sigint:
                self._logger.debug("astart: Restoring SIGINT handler")
                signal.signal(signal.SIGINT, old_sigint_handler)

        return self

    async def aclose(self) -> bool:
        if self.closed:
            self._logger.debug("aclose: App is already closed or hasn't been started. Skipping")
            return True

        self._logger.debug("Running <_aclose> method, shielding it from SIGINT and cancellation")

        hit_sigint = False

        def __handler(sig, frame):
            nonlocal hit_sigint
            hit_sigint = True

            self._logger.debug("SIGINT received while runnning <_aclose>; delaying")

        old_sigint_handler = None

        try:
            self._logger.debug("aclose: Replacing SIGINT handler")
            old_sigint_handler = signal.signal(signal.SIGINT, __handler)

            res = await asyncio.shield(self._aclose())

            if hit_sigint:
                self._logger.debug("aclose: Restoring SIGINT handler and re-rasing SIGINT")
                signal.signal(signal.SIGINT, old_sigint_handler)
                raise KeyboardInterrupt()

        finally:
            if not hit_sigint:
                self._logger.debug("aclose: Restoring SIGINT handler")
                signal.signal(signal.SIGINT, old_sigint_handler)

        if res is True:
            self._closed = True
            return True
        else:
            return False

    def start(self: _A) -> _A:
        return self.loop.run_until_complete(self.astart())

    def close(self) -> bool:
        res = self.loop.run_until_complete(self.aclose())

        if self._loop_started_by_self:
            # If the loop was started with AsyncApplication.run() mimic asyncio.run() behavior
            self._logger.warning(
                "The loop was started with AsyncApplication.run(), mimicing asyncio.run() behavior and force cancelling all tasks and closing the loop"
            )
            try:
                # Cancel all remaining uncompleted tasks (properly written subclass should never return any).
                self._cancel_all_tasks()

                # Shutdown all active asynchronous generators.
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            finally:
                self._logger.debug("Closing loop")
                self.loop.close()

        return res

    def _cancel_all_tasks(self):
        """
        Cancel all tasks in the loop (code from asyncio.run()).
        """

        to_cancel = asyncio.tasks.all_tasks(self._loop)
        self._logger.debug(f"Cancelling all remaining tasks in the loop. A totoal of {len(to_cancel)} tasks")

        if not to_cancel:
            return

        for task in to_cancel:
            task.cancel()

        self.loop.run_until_complete(asyncio.tasks.gather(*to_cancel, return_exceptions=True))

        for task in to_cancel:
            if task.cancelled():
                continue

            if task.exception() is not None:
                self.loop.call_exception_handler(
                    {
                        "message": f"unhandled exception during {self.__class__}.run() shutdown",
                        "exception": task.exception(),
                        "task": task,
                    }
                )

    async def _async_sigint_shield(
        self, func: Awaitable[_T], *, ensure_func_run: bool = False, close: bool = True
    ) -> _T | None:
        self._logger.debug(f"Running a sigint shielded class method {func}. {ensure_func_run=};{close=}")

        func_task: asyncio.Task | None = None
        hit_sigint = False

        def __handler(sig, frame):
            nonlocal hit_sigint
            hit_sigint = True

            if ensure_func_run:
                self._logger.debug("SIGINT received while runnning a shielded method; delaying")
            else:
                self._logger.debug("SIGINT received while runnning a shielded method; cancelling {func} immediately")
                if func_task:
                    func_task.cancel()

        self._logger.debug("Entering DelayedKeyboardInterrupt context")
        old_sigint_handler = signal.signal(signal.SIGINT, __handler)
        try:
            func_task = self.loop.create_task(func)
            return await func_task
        except asyncio.CancelledError:
            res = True

            if close:
                self._logger.warn("{func} was cancelled. Closing app")
                res = await self.aclose()

            if not res:
                raise

            return None
        finally:
            self._logger.debug("Exiting DelayedKeyboardInterrupt context. Restoring signal handlers")
            signal.signal(signal.SIGINT, old_sigint_handler)

            if hit_sigint:
                res = True

                if close:
                    self._logger.warn("Closing app after a delayed SIGINT")
                    res = await self.aclose()

                if not res:
                    raise

                return None

    def _run_coro(self, coro: Awaitable[_T]) -> _T:
        loop = self.loop

        if loop.is_running():
            self._logger.debug(f"Running coroutine {coro} on an already running loop")
            task = loop.create_task(coro)
            while not task.done():
                sleep(0.1)

            return task.result()
        else:
            self._logger.debug(f"Running loop until coroutine {coro} is complete")
            return self.loop.run_until_complete(coro)

    def __enter__(self: _A) -> _A:
        self._logger.debug("Entering regular (non-async) context")
        return self._run_coro(self.__aenter__())

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self._logger.debug("Exiting regular (non-async) context")
        return self._run_coro(self.__aexit__(exc_type, exc_value, traceback))

    async def __aenter__(self: _A) -> _A:
        self._logger.debug("Entering async context")
        return await self.astart()

    async def __aexit__(self, exc_type, exc_value, traceback) -> bool:
        self._logger.debug("Exiting async context")
        if exc_type and exc_type != KeyboardInterrupt:
            self._logger.error(
                "Exception caught before application was closed", exc_info=(exc_type, exc_value, traceback)
            )

        return await self.aclose()
