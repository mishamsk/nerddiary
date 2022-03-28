from __future__ import annotations

import abc
import asyncio
import logging
import signal
from time import sleep

from typing import Any, Coroutine, TypeVar

# from .delayedsignal import DelayedKeyboardInterrupt


_T = TypeVar("_T")
_A = TypeVar("_A", bound="AsyncApplication")


class AsyncApplication(abc.ABC):
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        logger: logging.Logger | None = None,
    ):
        self._loop: asyncio.AbstractEventLoop | None = loop
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._loop_started_by_self = False
        self._closed: asyncio.Future[bool] | None = None
        self._closing = False
        self._started = False

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
    def started(self) -> bool:
        return self._started

    @property
    def closed(self) -> bool:
        # This app has never been started
        if self._closed is None:
            return True

        # If we tried closing, return if it succeeded
        if self._closed.done():
            return self._closed.result()

        return False

    def run(self) -> Any:
        res = None

        try:
            self._logger.debug("Executing app startup sequence")
            if self.start() is not None:
                self._logger.debug("Running the app")
                res = self._run_coro(self._arun())
        except KeyboardInterrupt:
            raise
        except BaseException:
            self._logger.exception("Unhandled exception while running the app.")
            raise
        finally:
            self._logger.debug("Closing the app")
            self.close()

        return res

    @abc.abstractmethod
    async def _astart(self) -> bool:
        pass

    @abc.abstractmethod
    async def _aclose(self) -> bool:
        pass

    async def _arun(self) -> Any:
        raise NotImplementedError()

    async def astart(self: _A) -> _A:
        """Srarts the app

        Raises:
            RuntimeError: if the app is started after unsuccesful/unfinished close

        Returns:
            app instance
        """
        self._logger.debug(
            "Running <_astart> method, ensuring <aclose> is executed if SIGINT is sent before <_astart> is finished"
        )

        if self._started:
            self._logger.debug("App is already started. Skipping")
            return self

        if not self.closed:
            self._logger.error("The app hasn't been properly closed, thus it can't be restarted")
            raise RuntimeError("The app hasn't been properly closed, thus it can't be restarted")

        self._closed = asyncio.Future()

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
            self._logger.debug("Replacing SIGINT handler")
            old_sigint_handler = signal.signal(signal.SIGINT, __handler)

            func_task = self.loop.create_task(self._astart())

            self._started = await func_task
        except asyncio.CancelledError:
            if hit_sigint:
                self._logger.warn("Closing app after SIGINT")
            else:
                self._logger.warn("<_astart> was cancelled. Closing app")

            res = await self.aclose()

            if hit_sigint:
                self._logger.debug("Restoring SIGINT handler and re-rasing SIGINT")
                signal.signal(signal.SIGINT, old_sigint_handler)
                raise KeyboardInterrupt()

            if not res:
                raise
        except Exception:
            self._logger.exception("Uncaught exception in <_astart> method")
        finally:
            if not hit_sigint:
                self._logger.debug("Restoring SIGINT handler")
                signal.signal(signal.SIGINT, old_sigint_handler)

        return self

    async def aclose(self) -> bool:
        if self.closed:
            self._logger.debug("App is already closed or hasn't been started. Skipping")
            return True

        if self._closing:
            if self._closed is None:
                return True

            await self._closed
            return self.closed
        else:
            self._closed = asyncio.Future()
            self._closing = True

        self._logger.debug("Running <_aclose> method, shielding it from SIGINT and cancellation")

        hit_sigint = False

        def __handler(sig, frame):
            nonlocal hit_sigint
            hit_sigint = True

            self._logger.debug("SIGINT received while runnning <_aclose>; delaying")

        old_sigint_handler = None

        res = False
        try:
            self._logger.debug("Replacing SIGINT handler")
            old_sigint_handler = signal.signal(signal.SIGINT, __handler)

            res = await asyncio.shield(self._aclose())

            if hit_sigint:
                self._logger.debug("Restoring SIGINT handler and re-raising SIGINT")
                signal.signal(signal.SIGINT, old_sigint_handler)
                raise KeyboardInterrupt()
        except asyncio.CancelledError:
            self._logger.exception("Unhandled asyncio cancellation in <_aclose> method")
        except Exception:
            self._logger.exception("Uncaught exception in <_aclose> method")
        finally:
            if not hit_sigint:
                self._logger.debug("Restoring SIGINT handler")
                signal.signal(signal.SIGINT, old_sigint_handler)

        self._started = False
        self._closing = False
        self._closed.set_result(res)
        return self.closed

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

    def _run_coro(self, coro: Coroutine[Any, Any, _T]) -> _T:
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
