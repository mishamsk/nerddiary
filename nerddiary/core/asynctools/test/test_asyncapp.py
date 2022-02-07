from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from nerddiary.core.asynctools.asyncapp import AsyncApplication

import pytest


class MockAsyncApp(AsyncApplication):
    def __init__(self, *, loop: asyncio.AbstractEventLoop = None, logger: logging.Logger = None):
        super().__init__(loop=loop, logger=logger)

    async def _astart(self):
        self._logger.info("_astart")
        print("_astart")

    async def _aclose(self) -> bool:
        self._logger.info("_aclose")
        print("_aclose")
        return True

    async def _arun(self) -> str:
        self._logger.info("_arun")
        print("_arun")
        return "runned"


class MockFailingAsyncApp(AsyncApplication):
    def __init__(self, *, loop: asyncio.AbstractEventLoop = None, logger: logging.Logger = None):
        super().__init__(loop=loop, logger=logger)

    async def _astart(self):
        self._logger.info("_astart")
        print("_astart")

    async def _aclose(self) -> bool:
        self._logger.info("_aclose")
        print("_aclose")
        return False

    async def _arun(self) -> str:
        print("_arun")
        raise ValueError("Expected")


class MockSlowAsyncApp(AsyncApplication):
    def __init__(
        self,
        slow_start: int = 1,
        slow_close: int = 1,
        slow_run: int = 1,
        *,
        loop: asyncio.AbstractEventLoop = None,
        logger: logging.Logger = None,
    ):
        super().__init__(loop=loop, logger=logger)

        self._slow_start = slow_start
        self._slow_close = slow_close
        self._slow_run = slow_run

    async def _astart(self):
        self._logger.info("_astart")
        print("_astart")
        await asyncio.sleep(self._slow_start)

    async def _aclose(self) -> bool:
        self._logger.info("_aclose")
        print("_aclose")
        await asyncio.sleep(self._slow_close)
        return True

    async def _arun(self) -> str:
        self._logger.info("_arun")
        print("_arun")
        await asyncio.sleep(self._slow_run)
        return "runned"


@pytest.fixture
def test_logger(tmp_path: Path):
    log_file = tmp_path / "log"
    logger = logging.getLogger("pytest")
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.FileHandler(log_file))
    return (log_file, logger)


def test_abstract():
    with pytest.raises(TypeError, match=r"Can't instantiate abstract class.*"):
        AsyncApplication()  # type: ignore


async def test_using_external_loop_explicit(event_loop):
    ma = MockAsyncApp(loop=event_loop)
    assert ma.loop == event_loop


async def test_using_external_loop_implicit(event_loop):
    ma = MockAsyncApp()
    assert ma.loop == event_loop


def test_closed_property():
    ma = MockAsyncApp()
    assert ma.closed

    postpone = None
    with MockAsyncApp() as ma:
        assert not ma.closed
        postpone = ma

    assert postpone.closed


def test_start_no_interrupt():
    ma = MockAsyncApp().start()
    assert not ma.closed


def run_start_interrupt():
    MockSlowAsyncApp(slow_start=1).start()


def test_start_interrupt(interrupt_with_sigal):
    exitcode, out, err = interrupt_with_sigal(run_start_interrupt, 0.5, signal.SIGINT)
    log_lines = out.splitlines()
    assert (
        exitcode == 1
        and len(log_lines) == 2
        and log_lines[0] == "_astart"
        and log_lines[1] == "_aclose"
        and err.endswith("KeyboardInterrupt\n")
    )


def test_close_no_interrupt():
    ma = MockAsyncApp().start()
    assert not ma.closed
    ma.close()
    assert ma.closed


def test_run_no_interrupt(test_logger):
    log_file, logger = test_logger
    assert isinstance(log_file, Path)
    assert isinstance(logger, logging.Logger)

    res = MockAsyncApp(logger=logger).run()
    log_lines = log_file.read_text().splitlines()
    assert (
        len(log_lines) == 4
        and log_lines[0] == "_astart"
        and log_lines[1] == "_arun"
        and log_lines[2] == "_aclose"
        and log_lines[3]
        == "The loop was started with AsyncApplication.run(), mimicing asyncio.run() behavior and force cancelling all tasks and closing the loop"
        and res == "runned"
    )


async def test_async_context_no_interrupt(test_logger):
    log_file, logger = test_logger
    assert isinstance(log_file, Path)
    assert isinstance(logger, logging.Logger)

    async with MockAsyncApp(logger=logger):
        pass

    log_lines = log_file.read_text().splitlines()
    assert len(log_lines) == 2 and log_lines[0] == "_astart" and log_lines[1] == "_aclose"
