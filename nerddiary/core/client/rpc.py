import asyncio
import uuid

import typing as t


class AsyncResult:
    def __init__(self, id: uuid.UUID) -> None:
        self._id = id
        self._fut = asyncio.Future()

    async def get(self) -> t.Any:
        return await self._fut
