import logging

from .session.session import SessionSpawner

import typing as t


class ServerProtocol(t.Protocol):
    @property
    def _sessions(self) -> SessionSpawner:
        ...

    @property
    def _logger(self) -> logging.Logger:
        ...
