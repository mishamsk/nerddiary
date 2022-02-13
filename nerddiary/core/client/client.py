from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import suppress

from jsonrpcclient.requests import request_uuid
from jsonrpcclient.responses import Error, Ok, parse
from pydantic import ValidationError
from websockets import client
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from ..asynctools.asyncapp import AsyncApplication
from ..asynctools.asyncresult import AsyncResult
from ..client.config import NerdDiaryClientConfig
from ..server.rpc import RPCErrors
from ..server.schema import NotificationType, UserSessionSchema

import typing as t

logger = logging.getLogger(__name__)


class NerdDiaryClient(AsyncApplication):
    def __init__(
        self, *, config: NerdDiaryClientConfig = NerdDiaryClientConfig(), loop: asyncio.AbstractEventLoop = None
    ) -> None:
        super().__init__(loop=loop, logger=logger)

        self._id = uuid.uuid4()
        self._config = config
        self._running = False
        self._connect_lock = asyncio.Lock()
        self._ws: client.WebSocketClientProtocol | None = None
        self._message_dispatcher: asyncio.Task | None = None
        self._rpc_calls: t.Dict[uuid.UUID, AsyncResult] = {}
        self._load_sessions_on_connect: asyncio.Task | None = None
        self._sessions: t.Dict[str, UserSessionSchema] = {}

    async def _astart(self):
        logger.debug("Starting NerdDiary client")
        self._running = True
        await self._connect()
        self._message_dispatcher = asyncio.create_task(self._message_dispatch())

    async def _aclose(self) -> bool:
        logger.debug("Closing NerdDiary client")
        if self._running:
            # Stop any internal loops
            self._stop()

        # If we are still waiting for sessions on connect, wait for it to stop
        if self._load_sessions_on_connect and self._load_sessions_on_connect.cancel():
            logger.debug("Waiting for Load Sessions on Connect task to gracefully finish")
            with suppress(asyncio.CancelledError):
                await self._load_sessions_on_connect

        # If rpc dispatcher exist, wait for it to stop
        if self._message_dispatcher and self._message_dispatcher.cancel():
            logger.debug("Waiting for message dispatcher to gracefully finish")
            with suppress(asyncio.CancelledError):
                await self._message_dispatcher

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
                    self._ws = await client.connect(self._config.server_uri + str(self._id))
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

            self._load_sessions_on_connect = asyncio.create_task(self._get_sessions())

            logger.debug(
                f"Succesfully connected to NerdDiary server at <{self._config.server_uri}>, on try #{str(retry+1)}"
            )

    async def _disconnect(self):
        if self._ws is not None:
            logger.debug(f"Disconnecting from NerdDiary server at <{self._config.server_uri}>")
            await self._ws.close()

    async def _run_rpc(
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
            # TODO: this doesn't stop client + server is not closing gracefully on uvicorn reload
            raise ConnectionError(err)

        try:
            logger.debug(
                f"Waiting for RPC call result. Method <{method}> with params <{str(params)}>. Assigned JSON RPC id: {str(id)}"
            )
            res = await self._rpc_calls[id].get()
            return res
        except asyncio.CancelledError:
            pass
        finally:
            del self._rpc_calls[id]

    async def _message_dispatch(self):
        while self._running:
            try:
                # TODO: this doesn't support batch calls (when incoming is a list of dicts)
                raw_response = await self._ws.recv()
                parsed_response = json.loads(raw_response)

                if "notification" in parsed_response:
                    # Process notification
                    try:
                        n_type = NotificationType(int(parsed_response["notification"]))
                    except ValueError:
                        n_type = -1
                    match n_type:
                        case NotificationType.CLIENT_CONNECTED:
                            logger.debug(f"Recieved <{n_type.name}> notification. Ignoring")
                        case NotificationType.CLIENT_DISCONNECTED:
                            logger.debug(f"Recieved <{n_type.name}> notification. Ignoring")
                        case NotificationType.SESSION_UPDATE:
                            logger.debug(f"Recieved <{n_type.name}> notification. Processing")
                            await self._process_session_update(parsed_response["data"])
                        case _:
                            logger.debug(
                                f"Recieved unsupported notification <{parsed_response['notification']}>. Ignoring"
                            )
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

    def _stop(self):
        self._running = False

    async def _process_session_update(self, raw_ses: t.Dict[str, t.Any]):
        try:
            ses = UserSessionSchema.parse_obj(raw_ses)
            user_id = ses.user_id

            local_ses = self._sessions.get(user_id)
            if local_ses:
                if local_ses.user_status == ses.user_status:
                    return

                # TODO: processing of session status changes
            else:
                self._sessions[user_id] = ses
        except ValidationError:
            logger.error("Received incorrect session data from the server")
            raise RuntimeError("Received incorrect session data from the server")

    async def _get_sessions(self):
        raw_ses = await self._run_rpc("get_sessions")
        raw_ses_list: t.List[t.Dict[str, t.Any]] = json.loads(raw_ses)
        for raw_ses in raw_ses_list:
            await self._process_session_update(raw_ses)

    async def get_session(self, user_id: str) -> UserSessionSchema:
        local_ses = self._sessions.get(user_id)

        if not local_ses:
            try:
                local_ses = UserSessionSchema.parse_raw(await self._run_rpc("get_session", params={"user_id": user_id}))
                self._sessions[user_id] = local_ses
            except ValidationError:
                logger.error("Received incorrect session data from the server")
                raise RuntimeError("Received incorrect session data from the server")

        return local_ses

    async def unlock_session(self, session: UserSessionSchema, password: str) -> bool:
        try:
            return await self._run_rpc("unlock_session", params={"user_id": session.user_id, "password": password})
        except RuntimeError as err:
            logger.debug("RPC Call Error: " + str(err))
            if err.args[0] == RPCErrors.SESSION_NOT_FOUND:
                return False
            else:
                return False
