from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import suppress

from nerddiary.server.rpc import RPCErrors
from nerddiary.server.session.status import UserSessionStatus

from jsonrpcclient.requests import request_uuid
from jsonrpcclient.responses import Error, Ok, parse
from pydantic import ValidationError
from websockets import client
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK, InvalidMessage

from ..asynctools.asyncapp import AsyncApplication
from ..client.config import NerdDiaryClientConfig
from ..server.schema import NotificationType, UserSessionSchema
from ..utils.sensitive import mask_sensitive
from .rpc import AsyncRPCResult, RPCError

import typing as t


class NerdDiaryClient(AsyncApplication):
    def __init__(
        self,
        notification_callback: t.Callable[[NotificationType, t.Dict[str, t.Any]], t.Coroutine[t.Any, t.Any, None]]
        | None = None,
        *,
        config: NerdDiaryClientConfig = NerdDiaryClientConfig(),
        loop: asyncio.AbstractEventLoop = None,
        logger: logging.Logger = logging.getLogger(__name__),
    ) -> None:
        super().__init__(loop=loop, logger=logger)

        self._id = uuid.uuid4()
        self._config = config
        self._running = False
        self._connect_lock = asyncio.Lock()
        self._ws: client.WebSocketClientProtocol | None = None
        self._message_dispatcher: asyncio.Task | None = None
        self._rpc_calls: t.Dict[uuid.UUID, AsyncRPCResult] = {}
        self._sessions: t.Dict[str, UserSessionSchema] = {}
        self._notification_callback = notification_callback

    async def _astart(self):
        self._logger.debug("Starting NerdDiary client")
        self._running = True
        if await self._connect():
            self._message_dispatcher = asyncio.create_task(self._message_dispatch())
        else:
            raise RuntimeError("Couldn't connect to NerdDiary Server")

    async def _aclose(self) -> bool:
        with suppress(asyncio.CancelledError):
            self._logger.debug("Closing NerdDiary client")
            if self._running:
                # Stop any internal loops
                self._stop()

            # If rpc dispatcher exist, wait for it to stop
            if self._message_dispatcher and self._message_dispatcher.cancel():
                self._logger.debug("Waiting for message dispatcher to gracefully finish")
                await self._message_dispatcher

            # Cancel pending rpc_calls
            self._logger.debug(f"Cancelling pending RPC calls (result awaits). Total count: {len(self._rpc_calls)}")
            for id, pending_call in self._rpc_calls.items():
                pending_call._fut.cancel()
                self._rpc_calls.pop(id)

            # Disconnect websocket
            await self._disconnect()

        return True

    async def _connect(self) -> bool:
        async with self._connect_lock:
            retry = 0

            while (
                self._running and (self._ws is None or not self._ws.open) and retry < self._config.max_connect_retries
            ):
                self._logger.debug(
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
                except ConnectionResetError:
                    await asyncio.sleep(self._config.reconnect_timeout)
                    retry += 1
                except InvalidMessage:
                    await asyncio.sleep(self._config.reconnect_timeout)
                    retry += 1
                except OSError:
                    await asyncio.sleep(self._config.reconnect_timeout)
                    retry += 1
                except EOFError:
                    await asyncio.sleep(self._config.reconnect_timeout)
                    retry += 1
                except Exception:
                    err = "Unexpected exception while connecting to NerdDiary Server"
                    self._logger.exception(err)
                    break

            if (self._ws is None or not self._ws.open) and self._running:
                # failed to reconnect in time and the client is still running
                err = f"Failed to connect to NerdDiary server after {retry * self._config.reconnect_timeout} seconds (over {retry} retries). Closing client"
                self._logger.error(err)
                await self.aclose()
                return False

            self._logger.debug(
                f"Succesfully connected to NerdDiary server at <{self._config.server_uri}>, on try #{str(retry+1)}"
            )
            return True

    async def _disconnect(self):
        if self._ws is not None:
            self._logger.debug(f"Disconnecting from NerdDiary server at <{self._config.server_uri}>")
            await self._ws.close()

    async def _run_rpc(
        self,
        method: str,
        params: t.Union[t.Dict[str, t.Any], t.Tuple[t.Any, ...], None] = None,
    ) -> t.Any:
        req = request_uuid(method=method, params=params)
        id = req["id"]
        self._logger.debug(
            f"Executing RPC call on NerdDiary server. Method <{method}> with params <{mask_sensitive(str(params))}>. Assigned JSON RPC id: {str(id)}"
        )
        self._rpc_calls[id] = AsyncRPCResult(id=id)

        has_sent = False
        while not has_sent and self._running:
            try:
                await self._ws.send(json.dumps(req))
                has_sent = True
            except ConnectionClosedOK:
                if not await self._connect():
                    return
            except ConnectionClosedError:
                if not await self._connect():
                    return
            except Exception:
                err = "Unexpected exception while sending rpc call."
                self._logger.exception(err)
                raise RuntimeError(err)

        try:
            self._logger.debug(
                f"Waiting for RPC call result. Method <{method}> with params <{mask_sensitive(str(params))}>. Assigned JSON RPC id: {str(id)}"
            )
            res = await self._rpc_calls[id].get(timeout=self._config.rpc_call_timeout)
            self._logger.debug(f"RPC call result {mask_sensitive(str(res))}")
            return res
        except asyncio.CancelledError:
            pass
        except RPCError:
            raise
        except Exception:
            err = "Unexpected exception while waiting for rpc call result"
            self._logger.exception(err)
            raise RuntimeError(err)
        finally:
            self._rpc_calls.pop(id)

    async def _message_dispatch(self):
        self._logger.debug("Starting message dispatcher")

        while self._running:
            try:
                raw_response = await self._ws.recv()
                self._logger.debug(f"Recieved message <{mask_sensitive(str(raw_response))}>")
                parsed_response = json.loads(raw_response)

                if "notification" in parsed_response:
                    # Process notification
                    try:
                        n_type = NotificationType(int(parsed_response["notification"]))
                    except ValueError:
                        n_type = -1

                    match n_type:
                        case -1:
                            self._logger.debug(
                                f"Recieved unsupported notification <{parsed_response['notification']}>. Ignoring"
                            )
                        case NotificationType.SESSION_UPDATE:
                            self._logger.debug("Recieved session update. Processing")
                            asyncio.create_task(self._process_session_update(parsed_response["data"]))
                            if self._notification_callback:
                                asyncio.create_task(self._notification_callback(n_type, parsed_response["data"]))
                        case _:
                            self._logger.debug(f"Recieved <{n_type.name}> notification. Processing")
                            if self._notification_callback:
                                asyncio.create_task(self._notification_callback(n_type, parsed_response["data"]))
                else:
                    # Process RPC call response
                    match parse(parsed_response):
                        case Ok(result, id):
                            self._logger.debug(
                                f"RPC call response succesful with result <{mask_sensitive(str(result))}>. JSON RPC id: {id}"
                            )
                            if id not in self._rpc_calls:
                                self._logger.warning(
                                    f"RPC call response came too late and will be ignored. Result <{mask_sensitive(str(result))}>. JSON RPC id: {id}"
                                )
                                continue

                            self._rpc_calls[id]._fut.set_result(result)
                        case Error(code, message, data, id):
                            logging.error(
                                f"RPC call unsuccesful. Got error {code=} {message=} data={mask_sensitive(str(data))}. JSON RPC id: {id}"
                            )
                            if id not in self._rpc_calls:
                                self._logger.warning("RPC call response came too late from the server")
                                continue

                            self._rpc_calls[id]._fut.set_exception(RPCError(code, message, data))
            except ConnectionClosedOK:
                if not await self._connect():
                    return
            except ConnectionClosedError:
                if not await self._connect():
                    return
            except asyncio.CancelledError:
                break
            except Exception:
                err = "Unexpected exception during message dispatching."
                self._logger.exception(err)
                continue

    def _stop(self):
        self._running = False

    async def _process_session_update(self, raw_ses: t.Dict[str, t.Any]):
        try:
            ses = UserSessionSchema.parse_obj(raw_ses)
            user_id = ses.user_id

            local_ses = self._sessions.get(user_id)
            if local_ses:
                if ses.user_status == UserSessionStatus.LOCKED and local_ses.user_status > UserSessionStatus.LOCKED:
                    await self._run_rpc("unlock_session", params={"user_id": user_id, "key": local_ses.key})
                else:
                    self._sessions[user_id] = ses
            else:
                self._sessions[user_id] = ses
        except ValidationError:
            self._logger.exception("Received incorrect session data from the server")
            raise RuntimeError("Received incorrect session data from the server")

    async def get_session(self, user_id: str) -> UserSessionSchema | None:
        assert isinstance(user_id, str)
        local_ses = self._sessions.get(user_id)

        if not local_ses:
            try:
                res = await self._run_rpc("get_session", params={"user_id": str(user_id)})
                local_ses = UserSessionSchema.parse_raw(res)
                self._sessions[user_id] = local_ses
            except ValidationError:
                self._logger.exception("Received incorrect session data from the server")
            except RPCError:
                pass

        return local_ses

    async def exec_api_method(self, method: str, **params) -> t.Any:
        try:
            res = await self._run_rpc(method=method, params=params)
        except RPCError as r_err:
            if r_err.code > RPCErrors.ERROR_SERVER_ERROR:
                raise
            else:
                err = "Unexpected exception during execution of an API call."
                self._logger.exception(err)
                return None
        except Exception:
            err = "Unexpected exception during execution of an API call."
            self._logger.exception(err)
            return None

        return res
