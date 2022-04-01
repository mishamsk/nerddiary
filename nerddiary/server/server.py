from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from functools import partial

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi.websockets import WebSocket
from jsonrpcserver import async_dispatch
from pydantic.json import pydantic_encoder

from ..asynctools.asyncapp import AsyncApplication
from ..data.data import DataProvider
from ..utils.sensitive import mask_sensitive
from .config import NerdDiaryServerConfig
from .mixins.pollmixin import PollMixin
from .mixins.sessionmixin import SessionMixin
from .schema import ClientSchema, NotificationType, Schema, UserSessionSchema, generate_notification
from .session.session import SessionSpawner

from typing import Dict, Set, Tuple


class NerdDiaryServer(AsyncApplication, SessionMixin, PollMixin):
    def __init__(
        self,
        config: NerdDiaryServerConfig = NerdDiaryServerConfig(),
        loop: asyncio.AbstractEventLoop | None = None,
        logger: logging.Logger = logging.getLogger(__name__),
    ) -> None:
        super().__init__(loop=loop, logger=logger)

        self._config = config

        self._data_provider = DataProvider.get_data_provider(config.data_provider_name, config.data_provider_params)

        self._scheduler = AsyncIOScheduler()

        self._notification_queue: asyncio.Queue[
            Tuple[NotificationType, Schema | None, Set[str], str | None, str | None]
        ] = asyncio.Queue()
        self._notification_dispatcher = None

        self._sessions = SessionSpawner(
            data_provider=self._data_provider,
            notification_queue=self._notification_queue,
            scheduler=self._scheduler,
            logger=self._logger.getChild("sessions"),
        )

        self._actve_connections: Dict[str, WebSocket] = {}
        self._message_queue: asyncio.Queue[Tuple[str, str]] = asyncio.Queue()
        self._message_dispatcher: asyncio.Task | None = None

        self._running = False

    @property
    def message_queue(self) -> asyncio.Queue[Tuple[str, str]]:
        """Stores tuples of (client_id, raw message data)"""
        return self._message_queue

    async def _astart(self):
        self._logger.debug("Starting NerdDiary Server")

        self._scheduler.start()
        self._running = True
        self._notification_dispatcher = asyncio.create_task(self._notification_dispatch())
        self._message_dispatcher = asyncio.create_task(self._message_dispatch())

        await self._sessions.init_sessions()
        return True

    async def _aclose(self) -> bool:

        self._logger.debug("Closing NerdDiary server")
        if self._running:
            # Stop any internal loops
            self.stop()

        # If notification dispatcher exist, wait for it to stop
        if self._notification_dispatcher and self._notification_dispatcher.cancel():
            self._logger.debug("Waiting for Notification dispatcher to gracefully finish")
            with suppress(asyncio.CancelledError):
                await self._notification_dispatcher

        # Disconnect all clients
        for client in self._actve_connections:
            self._logger.debug(f"Disconecting {client=}")
            await self.disconnect_client(client)

        # If message dispatcher exist, wait for it to stop
        if self._message_dispatcher and self._message_dispatcher.cancel():
            self._logger.debug("Waiting for Websocket Message dispatcher to gracefully finish")
            with suppress(asyncio.CancelledError):
                await self._message_dispatcher

        # Shutdown the scheduler
        self._scheduler.shutdown(wait=False)
        await self._sessions.close()

        return True

    async def _notification_dispatch(self):
        self._logger.debug("Starting notification dispatcher")

        while self._running:
            type = data = exclude = source = target = None
            try:
                # Wait for clients
                if len(self._actve_connections) == 0:
                    self._logger.debug("Waiting for client connection")
                    await asyncio.sleep(1)

                type, data, exclude, source, target = await self._notification_queue.get()
                if target:
                    self._logger.debug(
                        f"Sending notification to client id <{target}>: {type=} data={mask_sensitive(str(data))} {source=} {exclude=}"
                    )
                    await self.send_personal_message(client_id=target, message=generate_notification(type, data))

                    self._logger.debug("Finished sending notification")
                else:
                    if source:
                        # Force exclude source form notification
                        exclude.add(source)
                    self._logger.debug(
                        f"Starting broadcasting notification: {type=} data={mask_sensitive(str(data))} {source=} {exclude=}"
                    )
                    await self.broadcast(generate_notification(type, data), exclude=exclude)

                    self._logger.debug("Finished broadcasting notification")
                self._notification_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception:
                self._logger.exception("Unexpected exception in notification dispatcher")

    async def _message_dispatch(self):
        self._logger.debug("Starting message dispatcher")

        client_id = None

        while self._running:
            try:
                client_id, raw_response = await self._message_queue.get()
                self._logger.debug(f"Recieved message <{mask_sensitive(raw_response)}>")
                ws = self._actve_connections.get(client_id)

                if not ws:
                    raise RuntimeError()

                parsed_response = json.loads(raw_response)
                if "method" in parsed_response:
                    # Execute local method (from RPC call)
                    self._logger.debug(
                        f"Processing incoming RPC call from a client {client_id=}. Method <{parsed_response['method']}>. JSON RPC id: {parsed_response['id']}"
                    )
                    if response := await async_dispatch(
                        raw_response, context=self, serializer=partial(json.dumps, default=pydantic_encoder)
                    ):
                        await ws.send_text(response)
                else:
                    # Process unrecognized message
                    self._logger.debug(f"Got unexpected message from a client {client_id=}. Ignoring")
            except RuntimeError:
                err = f"NerdDiary client connection terminated by a client {client_id=}. Skipping message"
                self._logger.error(err)
            except asyncio.CancelledError:
                break
            except Exception:
                self._logger.exception("Unexpected exception in message dispatcher")
                raise
            finally:
                try:
                    self._message_queue.task_done()
                except ValueError:
                    pass

    def stop(self):
        self._scheduler.pause()
        self._running = False

    async def disconnect_client(self, client_id: str):
        self._logger.debug(f"Disconnecting {client_id=} from NerdDiary server")
        ws = self._actve_connections[client_id]
        await ws.close()
        self._actve_connections.pop(client_id)
        await self.notify(
            NotificationType.SERVER_CLIENT_DISCONNECTED, ClientSchema(client_id=client_id), source=client_id
        )
        if len(self._actve_connections) == 0:
            await self._sessions.close()

    async def on_connect_client(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self._logger.debug(f"{client_id=} connected to NerdDiary server")
        self._actve_connections[client_id] = websocket
        self._logger.debug(f"Notifying other clients about {client_id=}")
        await self.notify(NotificationType.SERVER_CLIENT_CONNECTED, ClientSchema(client_id=client_id), source=client_id)
        self._logger.debug(f"Sending {client_id=} all existing sessions. A total of {len(self._sessions._sessions)}")
        for session in self._sessions.get_all():
            key = None
            if session._data_connection:
                key = session._data_connection.key.decode()
            await self.notify(
                NotificationType.SERVER_SESSION_UPDATE,
                UserSessionSchema(user_id=session.user_id, user_status=session.user_status, key=key),
                target=client_id,
            )

    async def on_disconnect_client(self, client_id: str):
        self._logger.debug(f"{client_id=} disconnected from NerdDiary server")
        self._actve_connections.pop(client_id)
        await self.notify(
            NotificationType.SERVER_CLIENT_DISCONNECTED, ClientSchema(client_id=client_id), source=client_id
        )

    async def broadcast(self, message: str | bytes, exclude: Set[str] = set()):
        self._logger.debug(
            f"Broadcasting message={mask_sensitive(message if isinstance(message, str) else message.decode())} to all clients except {exclude=}"
        )

        for client_id, ws in self._actve_connections.items():
            if client_id not in exclude:
                self._logger.debug(f"Sending tp {client_id=}")
                if isinstance(message, str):
                    await ws.send_text(message)
                else:
                    await ws.send_bytes(message)

    async def send_personal_message(self, client_id: str, message: str | bytes):
        self._logger.debug(
            f"Selnding message={mask_sensitive(message if isinstance(message, str) else message.decode())} to {client_id=}"
        )
        ws = self._actve_connections.get(client_id)
        if ws:
            if isinstance(message, str):
                await ws.send_text(message)
            else:
                await ws.send_bytes(message)

    async def notify(
        self,
        type: NotificationType,
        data: Schema | None = None,
        exclude: Set[str] = set(),
        source: str | None = None,
        target: str | None = None,
    ):
        await self._notification_queue.put((type, data, exclude, source, target))
