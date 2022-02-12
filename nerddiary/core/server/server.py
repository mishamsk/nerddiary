from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import suppress

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi.websockets import WebSocket
from jsonrpcclient.requests import request_uuid
from jsonrpcclient.responses import Error, Ok, parse
from jsonrpcserver import Result, Success, async_dispatch, method

from ..asynctools.asyncapp import AsyncApplication
from ..asynctools.asyncresult import AsyncResult
from ..data.data import DataProvider
from ..job.job import Job
from ..session.session import SessionSpawner, UserSession
from ..session.string import StringSessionSpawner
from .config import NerdDiaryServerConfig

from typing import Any, Callable, Coroutine, Dict, Tuple, Type, Union

# import typing as t

logger = logging.getLogger(__name__)


class NerdDiaryServer(AsyncApplication):
    def __init__(
        self,
        session: str | SessionSpawner = "default",
        config: NerdDiaryServerConfig = NerdDiaryServerConfig(),
        loop: asyncio.AbstractEventLoop = None,
    ) -> None:
        super().__init__(loop=loop, logger=logger)

        self._config = config

        self._data_provider = DataProvider.get_data_provider(config.data_provider_name, config.data_provider_params)

        self._scheduler = AsyncIOScheduler(jobstores={"default": SQLAlchemyJobStore(url=config.jobstore_sa_url)})

        self._job_queue: asyncio.Queue[Job] = asyncio.Queue()

        if isinstance(session, str):
            self._session_spawner = StringSessionSpawner(
                params=config.session_spawner_params,
                data_provider=self._data_provider,
                scheduler=self._scheduler,
                job_queue=self._job_queue,
            )
        else:
            self._session_spawner = session

        self._sessions: Dict[str, UserSession]

        self._running = False
        self._job_dispatcher = None
        self._job_subscribers: Dict[Type[Job], Callable[[Job], Coroutine[None, None, bool]]] = {}

        self._actve_connections: Dict[str, WebSocket] = {}
        self._message_queue: asyncio.Queue[Tuple[str, str]] = asyncio.Queue()
        self._rpc_dispatcher: asyncio.Task | None = None
        self._rpc_calls: Dict[uuid.UUID, AsyncResult] = {}

    @property
    def session(self) -> SessionSpawner:
        return self._session_spawner

    @property
    def message_queue(self) -> asyncio.Queue[Tuple[str, str]]:
        """Stores tuples of (client_id, raw message data)"""
        return self._message_queue

    async def _astart(self):
        logger.debug("Starting NerdDiary Server")

        self._scheduler.start()
        self._running = True
        self._job_dispatcher = asyncio.create_task(self._job_dispatch())
        self._rpc_dispatcher = asyncio.create_task(self._rpc_dispatch())

    async def _aclose(self) -> bool:
        logger.debug("Closing NerdDiary server")
        if self._running:
            # Stop any internal loops
            self.stop()

        # If job dispatcher exist, wait for it to stop
        if self._job_dispatcher and self._job_dispatcher.cancel():
            logger.debug("Waiting for Job dispatcher to gracefully finish")
            with suppress(asyncio.CancelledError):
                await self._job_dispatcher

        # Disconnect all clients
        for client in self._actve_connections:
            await self.disconnect_client(client)

        # If rpc dispatcher exist, wait for it to stop
        if self._rpc_dispatcher and self._rpc_dispatcher.cancel():
            logger.debug("Waiting for RPC dispatcher to gracefully finish")
            with suppress(asyncio.CancelledError):
                await self._rpc_dispatcher

        # Cancel pending rpc_calls
        logger.debug(f"Cancelling pending RPC calls (result awaits). Total count: {len(self._rpc_calls)}")
        for pending_call in self._rpc_calls.values():
            pending_call._fut.cancel()

        # Shutdown the scheduler
        self._scheduler.shutdown(wait=False)
        for ses in self._sessions.values():
            await ses.close()

        return True

    async def _job_dispatch(self):
        # TODO: this has to be redone on handling rpc callback calls. Use tasks to not block the job dispatch
        while self._running:
            try:
                # Wait for subscribers
                if len(self._job_subscribers):
                    await asyncio.sleep(1)

                job = await self._job_queue.get()

                res = False
                for type, callback in self._job_subscribers.items():
                    # Dispatch only if job type matches subscribed type
                    if not isinstance(job, type):
                        continue

                    try:
                        res = await callback(job)
                    except Exception as exc:
                        logger.warning(
                            f"Exception while processing job <{job}> with callback <{callback.__module__}.{callback.__name__}>",
                            exc_info=exc,
                        )

                    if res:
                        self._job_queue.task_done()
                        break

                if not res:
                    logger.warning(f"Job <{job}> failed to process by any of the subscribers. Skipping")
                    self._job_queue.task_done()

                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                break

    async def run_rpc(
        self,
        client_ws: WebSocket,
        method: str,
        params: Union[Dict[str, Any], Tuple[Any, ...], None] = None,
    ) -> Any:
        req = request_uuid(method=method, params=params)
        id = req["id"]
        logger.debug(
            f"Executing RPC call on NerdDiary client. Method <{method}> with params <{str(params)}>. Assigned JSON RPC id: {str(id)}"
        )
        self._rpc_calls[id] = AsyncResult(id=id)
        try:
            await client_ws.send_text(json.dumps(req))
        except RuntimeError:
            err = "NerdDiary client connection terminated by a client. Skipping message"
            logger.error(err)

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
        client_id = None

        while self._running:
            try:
                # TODO: this doesn't support batch calls (when incoming is a list of dicts)
                client_id, raw_response = await self._message_queue.get()
                ws = self._actve_connections.get(client_id)

                if not ws:
                    raise RuntimeError()

                parsed_response = json.loads(raw_response)
                if "method" in parsed_response:
                    # Execute local method (from RPC call)
                    logger.debug(
                        f"Processing incoming RPC call from a client {client_id=}. Method <{parsed_response['method']}> with params <{parsed_response['params']}>. JSON RPC id: {parsed_response['id']}"
                    )
                    if response := await async_dispatch(raw_response, context=self):
                        await ws.send_text(response)
                else:
                    # Process RPC call response
                    match parse(parsed_response):
                        case Ok(result, id):
                            logger.debug(
                                f"Processing RPC call response from a client {client_id=}. Result <{result}>. JSON RPC id: {id}"
                            )
                            self._rpc_calls[id]._fut.set_result(result)
                        case Error(code, message, data, id):
                            logging.error(message)
                            self._rpc_calls[id]._fut.set_exception(RuntimeError(code, message, data))
            except RuntimeError:
                err = f"NerdDiary client connection terminated by a client {client_id=}. Skipping message"
                logger.error(err)
            except asyncio.CancelledError:
                break
            finally:
                self._message_queue.task_done()

    def stop(self):
        self._scheduler.pause()
        self._running = False

    async def disconnect_client(self, client_id: str):
        logger.debug(f"Disconnecting {client_id=} from NerdDiary server")
        ws = self._actve_connections[client_id]
        await ws.close()
        self._actve_connections.pop(client_id)

    async def on_connect_client(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        logger.debug(f"{client_id=} connected to NerdDiary server")
        self._actve_connections[client_id] = websocket

    def on_disconnect_client(self, client_id: str):
        logger.debug(f"{client_id=} disconnected from NerdDiary server")
        self._actve_connections.pop(client_id)

    @method  # type:ignore
    async def ping(self, p) -> Result:
        print("Nds ws called from the server with param: " + str(p))
        return Success("pong " + str(p))
