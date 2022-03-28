import asyncio
import uuid

import typing as t


class AsyncRPCResult:
    def __init__(self, id: uuid.UUID) -> None:
        self._id = id
        self._fut = asyncio.Future()

    async def get(self, timeout: float = 5.0) -> t.Any:
        try:
            return await asyncio.wait_for(self._fut, timeout=timeout)
        except asyncio.TimeoutError:
            return
