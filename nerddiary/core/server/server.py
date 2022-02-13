from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi.websockets import WebSocket
from jsonrpcserver import Error, Result, Success, async_dispatch, method

from ..asynctools.asyncapp import AsyncApplication
from ..data.data import DataProvider
from .config import NerdDiaryServerConfig
from .rpc import RPCErrors
from .schema import ClientSchema, NotificationType, Schema, UserSessionSchema, generate_notification
from .session.session import SessionSpawner, UserSession
from .session.string import StringSessionSpawner

from typing import Any, Coroutine, Dict, List, Set, Tuple

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

        self._notification_queue: asyncio.Queue[
            Tuple[NotificationType, Schema | None, Set[str], str | None]
        ] = asyncio.Queue()
        self._notification_dispatcher = None

        if isinstance(session, str):
            self._session_spawner = StringSessionSpawner(
                params=config.session_spawner_params,
                data_provider=self._data_provider,
                notification_queue=self._notification_queue,
            )
        else:
            self._session_spawner = session

        self._sessions: Dict[str, UserSession] = {}

        self._actve_connections: Dict[str, WebSocket] = {}
        self._message_queue: asyncio.Queue[Tuple[str, str]] = asyncio.Queue()
        self._message_dispatcher: asyncio.Task | None = None

        self._running = False

    @property
    def message_queue(self) -> asyncio.Queue[Tuple[str, str]]:
        """Stores tuples of (client_id, raw message data)"""
        return self._message_queue

    async def _astart(self):
        logger.debug("Starting NerdDiary Server")

        self._scheduler.start()
        self._running = True
        self._notification_dispatcher = asyncio.create_task(self._notification_dispatch())
        self._message_dispatcher = asyncio.create_task(self._message_dispatch())

        self._sessions = await self._session_spawner.load_sessions()
        to_notify: List[Coroutine[Any, Any, None]] = []
        for user_id, ses in self._sessions.items():
            to_notify.append(
                self.notify(
                    NotificationType.SESSION_UPDATE, UserSessionSchema(user_id=user_id, user_status=ses.user_status)
                )
            )

        if to_notify:
            await asyncio.gather(*to_notify)

    async def _aclose(self) -> bool:
        logger.debug("Closing NerdDiary server")
        if self._running:
            # Stop any internal loops
            self.stop()

        # If notification dispatcher exist, wait for it to stop
        if self._notification_dispatcher and self._notification_dispatcher.cancel():
            logger.debug("Waiting for Notification dispatcher to gracefully finish")
            with suppress(asyncio.CancelledError):
                await self._notification_dispatcher

        # Disconnect all clients
        for client in self._actve_connections:
            await self.disconnect_client(client)

        # If message dispatcher exist, wait for it to stop
        if self._message_dispatcher and self._message_dispatcher.cancel():
            logger.debug("Waiting for Websocket Message dispatcher to gracefully finish")
            with suppress(asyncio.CancelledError):
                await self._message_dispatcher

        # Shutdown the scheduler
        self._scheduler.shutdown(wait=False)
        for ses in self._sessions.values():
            await ses.close()

        return True

    async def _notification_dispatch(self):
        while self._running:
            try:
                # Wait for clients
                if len(self._actve_connections) == 0:
                    logger.debug("Waiting for client connection")
                    await asyncio.sleep(1)

                type, data, exclude, source = await self._notification_queue.get()
                if source:
                    # Force exclude source form notification
                    exclude.add(source)
                logger.debug(f"Starting broadcasting notification: {type=} {data=} {source=} {exclude=}")
                await self.broadcast(generate_notification(type, data), exclude=exclude)

                logger.debug("Finished broadcasting notification")
                self._notification_queue.task_done()

            except asyncio.CancelledError:
                break

    async def _message_dispatch(self):
        client_id = None

        while self._running:
            try:
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
                    # Process unrecognized message
                    logger.debug(f"Got unexpected message <{raw_response}> from a client {client_id=}. Ignoring")
            except RuntimeError:
                err = f"NerdDiary client connection terminated by a client {client_id=}. Skipping message"
                logger.error(err)
            except asyncio.CancelledError:
                break
            finally:
                try:
                    self._message_queue.task_done()
                except ValueError:
                    pass

    def stop(self):
        self._scheduler.pause()
        self._running = False

    async def disconnect_client(self, client_id: str):
        logger.debug(f"Disconnecting {client_id=} from NerdDiary server")
        ws = self._actve_connections[client_id]
        await ws.close()
        self._actve_connections.pop(client_id)
        await self.notify(NotificationType.CLIENT_DISCONNECTED, ClientSchema(client_id=client_id), source=client_id)

    async def on_connect_client(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        logger.debug(f"{client_id=} connected to NerdDiary server")
        self._actve_connections[client_id] = websocket
        await self.notify(NotificationType.CLIENT_CONNECTED, ClientSchema(client_id=client_id), source=client_id)

    async def on_disconnect_client(self, client_id: str):
        logger.debug(f"{client_id=} disconnected from NerdDiary server")
        self._actve_connections.pop(client_id)
        await self.notify(NotificationType.CLIENT_DISCONNECTED, ClientSchema(client_id=client_id), source=client_id)

    async def broadcast(self, message: str, exclude: Set[str] = set()):
        for client_id, ws in self._actve_connections.items():
            if client_id not in exclude:
                await ws.send_text(message)

    async def notify(self, type: NotificationType, data: Schema = None, exclude: Set[str] = set(), source: str = None):
        await self._notification_queue.put((type, data, exclude, source))

    @method  # type:ignore
    async def get_sessions(self) -> Result:
        logger.debug("Processing RPC call")
        data = [
            UserSessionSchema(user_id=ses.user_id, user_status=ses.user_status).dict(exclude_unset=True)
            for ses in self._sessions.values()
        ]
        return Success(json.dumps(data))

    @method  # type:ignore
    async def get_session(self, user_id: str) -> Result:
        logger.debug("Processing RPC call")

        ses = self._sessions.get(user_id)

        if not ses:
            ses = await self._session_spawner.create_session(user_id=user_id)

        return Success(UserSessionSchema(user_id=ses.user_id, user_status=ses.user_status).json(exclude_unset=True))

    @method  # type:ignore
    async def unlock_session(self, user_id: str, password: str = None, key: str = None) -> Result:
        logger.debug("Processing RPC call")

        ses = self._sessions.get(user_id)

        if not ses:
            return Error(RPCErrors.SESSION_NOT_FOUND)

        bkey = None
        if key:
            bkey = key.encode()

        pass_or_key = bkey or password
        if not pass_or_key:
            return Error(RPCErrors.PASSWORD_AND_KEY_MISSING)

        res = await ses.unlock(pass_or_key)

        return Success(res)
