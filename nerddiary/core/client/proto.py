import logging

from ..server.schema import UserSessionSchema

import typing as t


class ClientProtocol(t.Protocol):
    @property
    def _sessions(self) -> t.Dict[str, UserSessionSchema]:
        ...

    @property
    def _logger(self) -> logging.Logger:
        ...

    async def _process_session_update(self, raw_ses: t.Dict[str, t.Any]):
        ...

    async def _run_rpc(
        self,
        method: str,
        params: t.Union[t.Dict[str, t.Any], t.Tuple[t.Any, ...], None] = None,
    ) -> t.Any:
        ...
