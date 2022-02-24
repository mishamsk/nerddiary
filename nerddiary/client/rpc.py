import asyncio
import uuid

from ..server.rpc import RPCErrors

import typing as t


class RPCError(Exception):
    def __init__(self, code: int, message: str, data: t.Any, *args: object) -> None:
        self.code = RPCErrors(code)
        self.message = message
        self.data = data
        super().__init__(*args)


class AsyncRPCResult:
    def __init__(self, id: uuid.UUID) -> None:
        self._id = id
        self._fut = asyncio.Future()

    async def get(self, timeout: float = 5.0) -> t.Any:
        try:
            return await asyncio.wait_for(self._fut, timeout=timeout)
        except asyncio.TimeoutError:
            return
