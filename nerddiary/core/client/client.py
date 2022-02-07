from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import suppress

from nerddiary.core.asynctools.asyncapp import AsyncApplication

# TODO: change to relative import
from nerddiary.core.client.config import NerdDiaryClientConfig

from jsonrpcclient.requests import request_uuid
from jsonrpcclient.responses import Error, Ok, parse
from jsonrpcserver import Result, Success, async_dispatch, method
from websockets import client
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

import typing as t

logger = logging.getLogger(__name__)


class AsyncResult:
    def __init__(self, id: uuid.UUID) -> None:
        self._id = id
        self._fut = asyncio.Future()

    async def get(self) -> t.Any:
        return await self._fut


class NerdDiaryClient(AsyncApplication):
    def __init__(
        self, *, config: NerdDiaryClientConfig = NerdDiaryClientConfig(), loop: asyncio.AbstractEventLoop = None
    ) -> None:
        super().__init__(loop=loop, logger=logger)

        self._config = config
        self._running = False
        self._connect_lock = asyncio.Lock()
        self._ws: client.WebSocketClientProtocol | None = None
        self._rpc_dispatcher: asyncio.Task | None = None
        self._rpc_calls: t.Dict[uuid.UUID, AsyncResult] = {}

    async def _astart(self):
        logger.debug("Starting NerdDiary client")
        self._running = True
        await self._connect()
        self._rpc_dispatcher = asyncio.create_task(self._rpc_dispatch())

    async def _aclose(self) -> bool:
        logger.debug("Closing NerdDiary client")
        if self._running:
            # Stop any internal loops
            self.stop()

        # If rpc dispatcher exist, wait for it to stop
        if self._rpc_dispatcher and self._rpc_dispatcher.cancel():
            logger.debug("Waiting for RPC dispatcher to gracefully finish")
            with suppress(asyncio.CancelledError):
                await self._rpc_dispatcher

        # Cancel pending rpc_calls
        logger.debug(f"Cancelling pending RPC calls (result awaits). Total count: {len(self._rpc_calls)}")
        for pending_call in self._rpc_calls.values():
            pending_call._fut.cancel()

        # Disconnect websocket
        await self._disconnect()

        return True

    async def _connect(self):
        async with self._connect_lock:
            retry = 0

            while self._running and self._ws is None and retry < self._config.max_connect_retries:
                logger.debug(
                    f"Trying to connect to NerdDiary server at <{self._config.server_uri}>, try #{str(retry+1)}"
                )
                try:
                    self._ws = await client.connect(self._config.server_uri)
                except TimeoutError:
                    await asyncio.sleep(self._config.reconnect_timeout)
                    retry += 1
                except ConnectionRefusedError:
                    await asyncio.sleep(self._config.reconnect_timeout)
                    retry += 1
                except OSError:
                    await asyncio.sleep(self._config.reconnect_timeout)
                    retry += 1

            if self._ws is None and self._running:
                # failed to reconnect in time and the client is still running
                err = f"Failed to connect to NerdDiary server after {retry * self._config.reconnect_timeout} seconds ({retry} retries)"
                logger.error(err)
                raise ConnectionError(err)

            logger.debug(
                f"Succesfully connected to NerdDiary server at <{self._config.server_uri}>, on try #{str(retry+1)}"
            )

    async def _disconnect(self):
        if self._ws is not None:
            logger.debug(f"Disconnecting from NerdDiary server at <{self._config.server_uri}>")
            await self._ws.close()

    async def run_rpc(
        self,
        method: str,
        params: t.Union[t.Dict[str, t.Any], t.Tuple[t.Any, ...], None] = None,
    ) -> t.Any:
        req = request_uuid(method=method, params=params)
        id = req["id"]
        logger.debug(
            f"Executing RPC call on NerdDiary server. Method <{method}> with params <{str(params)}>. Assigned JSON RPC id: {str(id)}"
        )
        self._rpc_calls[id] = AsyncResult(id=id)
        try:
            await self._ws.send(json.dumps(req))
        except ConnectionClosedOK:
            await self._connect()
        except ConnectionClosedError:
            err = "NerdDiary server connection terminated with an error. Exiting RPC call handler"
            logger.error(err)
            raise ConnectionError(err)

        try:
            logger.debug(
                f"Waiting for RPC call result. Method <{method}> with params <{str(params)}>. Assigned JSON RPC id: {str(id)}"
            )
            res = await self._rpc_calls[id].get()
            del self._rpc_calls[id]
            return res
        except asyncio.CancelledError:
            del self._rpc_calls[id]

    async def _rpc_dispatch(self):
        while self._running:
            try:
                # TODO: this doesn't support batch calls (when incoming is a list of dicts)
                raw_response = await self._ws.recv()
                parsed_response = json.loads(raw_response)
                if "method" in parsed_response:
                    # Execute local method (from RPC call)
                    logger.debug(
                        f"Processing incoming RPC call from the server. Method <{parsed_response['method']}> with params <{parsed_response['params']}>. JSON RPC id: {parsed_response['id']}"
                    )
                    if response := await async_dispatch(raw_response, context=self):
                        await self._ws.send(response)
                else:
                    # Process RPC call response
                    match parse(parsed_response):
                        case Ok(result, id):
                            logger.debug(
                                f"Processing RPC call response from the server. Result <{result}>. JSON RPC id: {id}"
                            )
                            self._rpc_calls[id]._fut.set_result(result)
                        case Error(code, message, data, id):
                            logging.error(message)
                            self._rpc_calls[id]._fut.set_exception(RuntimeError(code, message, data))
            except ConnectionClosedOK:
                await self._connect()
            except ConnectionClosedError:
                err = "NerdDiary server connection terminated with an error. Exiting rpc dispatcher"
                logger.error(err)
                raise ConnectionError(err)
            except asyncio.CancelledError:
                break

    def stop(self):
        self._running = False

    @method  # type:ignore
    async def ping(self, p) -> Result:
        print("Ndc ws called from the server with param: " + str(p))
        return Success("pong " + str(p))


if __name__ == "__main__":
    import sys
    from time import sleep

    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler(stream=sys.stdout))

    with NerdDiaryClient() as ndc:
        for i in range(10):
            try:
                print(ndc.loop.run_until_complete(ndc.run_rpc("ping", params={"p": str(i)})))
            except RuntimeError as e:
                print(str(e))
            except ConnectionError as e:
                print(str(e))
                break
            sleep(1)
