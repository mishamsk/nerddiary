from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import os
import time
from types import ModuleType

from typing import TYPE_CHECKING, Coroutine

if TYPE_CHECKING:
    from ..bot import NerdDiaryTGBot


async def init(*, bot: NerdDiaryTGBot, root_logger: logging.Logger, **kwargs):
    logger = root_logger.getChild("handlers")

    plugins = [
        # Dynamically import
        importlib.import_module(".", f"{__name__}.{file[:-3]}")
        # All the files in the current directory
        for file in os.listdir(os.path.dirname(__file__))
        # If they start with a letter and are Python files
        if file[0].isalpha() and file.endswith(".py")
    ]

    # Keep a mapping of module name to module for easy access inside the plugins
    modules = {m.__name__.split(".")[-1]: m for m in plugins}

    # All kwargs provided to get_init_args are those that plugins may access
    to_init = (get_init_coro(plugin, logger=logger, bot=bot, modules=modules, **kwargs) for plugin in plugins)

    # Plugins may not have a valid init so those need to be filtered out
    await asyncio.gather(*(filter(None, to_init)))


def get_init_coro(plugin: ModuleType, logger: logging.Logger, **kwargs) -> Coroutine[None, None, None] | None:
    p_init = getattr(plugin, "init", None)
    if not callable(p_init):
        return None

    kwargs["logger"] = logger
    result_kwargs = {}
    sig = inspect.signature(p_init)
    for param in sig.parameters:
        if param in kwargs:
            result_kwargs[param] = kwargs[param]
        else:
            logger.warning("Plugin %s has unknown init parameter %s. Skipping", plugin.__name__, param)
            return None

    return _init_plugin(plugin, logger, result_kwargs)


async def _init_plugin(plugin: ModuleType, logger: logging.Logger, kwargs):
    try:
        logger.debug(f"Loading plugin {plugin.__name__}…")
        start = time.time()
        await plugin.init(**kwargs)
        took = time.time() - start
        logger.debug(f"Loaded plugin {plugin.__name__} (took {took:.2f}s)")
    except Exception:
        logger.exception(f"Failed to load plugin {plugin}")
