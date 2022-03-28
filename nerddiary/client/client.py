from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from contextlib import suppress

from jsonrpcclient.requests import request_uuid
from jsonrpcclient.responses import Error, Ok, parse
from pydantic import ValidationError
from websockets import client
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK, InvalidMessage

from ..asynctools.asyncapp import AsyncApplication
from ..client.config import NerdDiaryClientConfig
from ..error.error import NerdDiaryError, NerdDiaryErrorCode
from ..server.schema import NotificationType, Schema, UserSessionSchema
from ..server.session.status import UserSessionStatus
from ..utils.sensitive import mask_sensitive
from .rpc import AsyncRPCResult

import typing as t


class StopNotificationPropagation(Exception):
    pass


class NerdDiaryClient(AsyncApplication):
    def __init__(
        self,
        *,
        config: NerdDiaryClientConfig = NerdDiaryClientConfig(),
        loop: asyncio.AbstractEventLoop | None = None,
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
        self._notification_handlers: t.DefaultDict[
            NotificationType,
            t.List[t.Callable[[NotificationType, Schema | None], t.Coroutine[t.Any, t.Any, None]]],
        ] = defaultdict(list)
        self._notification_handler_tasks: t.Set[asyncio.Task] = set()

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._ws.open

    def on(self, notification_type: NotificationType):
        """Decorator used to add notification handler. Handler must accept two arguments: `NotificationType` and a data dict

        Args:
            notification_type (NotificationType): notification type to handle
        """

        def decorator(f):
            self._notification_handlers[notification_type].append(f)
            return f

        return decorator

    async def _astart(self) -> bool:
        self._logger.debug("Starting NerdDiary client")
        self._running = True
        if await self._connect():
            self._message_dispatcher = asyncio.create_task(self._message_dispatch())
            return True
        else:
            self._logger.warning("Couldn't connect to NerdDiary Server")
            return False

    async def _aclose(self) -> bool:

        self._logger.debug("Closing NerdDiary client")

        # Disconnect websocket first, this will allow handling client_on_disconnect notification and send the last message to the server (if connected)
        self._logger.debug("Disconnecting websocket")
        await self._disconnect()

        if self._running:
            self._logger.debug("Stopping internal loops")
            # Stop any internal loops
            self._stop()

        # If rpc dispatcher exist, wait for it to stop
        if self._message_dispatcher and not self._message_dispatcher.done() and self._message_dispatcher.cancel():
            self._logger.debug("Waiting for message dispatcher to gracefully finish")
            with suppress(asyncio.CancelledError):
                await self._message_dispatcher

        # Cancel pending rpc_calls
        self._logger.debug(f"Cancelling pending RPC calls (result awaits). Total count: {len(self._rpc_calls)}")
        for id, pending_call in self._rpc_calls.items():
            pending_call._fut.cancel()
            self._rpc_calls.pop(id)

        # Cancel all notification handler tasks
        for task in self._notification_handler_tasks:
            if not task.done() and task.cancel():
                self._logger.debug(f"Waiting for {task!r} to gracefully finish")
                with suppress(asyncio.CancelledError):
                    await task

        # Clearing handler task list
        self._notification_handler_tasks = set()

        return True

    async def _connect(self) -> bool:
        async with self._connect_lock:
            retry = 0

            await self._process_notification(NotificationType.CLIENT_BEFORE_CONNECT)
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
                await self._process_notification(NotificationType.CLIENT_CONNECT_FAILED)
                await asyncio.shield(self.aclose())
                return False

            await self._process_notification(NotificationType.CLIENT_ON_CONNECT)
            self._logger.debug(
                f"Succesfully connected to NerdDiary server at <{self._config.server_uri}>, on try #{str(retry+1)}"
            )
            return True

    async def _disconnect(self):
        if self._ws is not None and self._ws.open:
            self._logger.debug(f"Disconnecting from NerdDiary server at <{self._config.server_uri}>")
            await self._process_notification(NotificationType.CLIENT_BEFORE_DISCONNECT)
            await self._ws.close()
            await self._process_notification(NotificationType.CLIENT_ON_DISCONNECT)

    async def _run_rpc(
        self,
        method: str,
        params: t.Union[t.Dict[str, t.Any], t.Tuple[t.Any, ...], None] = None,
    ) -> t.Any:
        req = request_uuid(method=method, params=params)
        id = req["id"]
        self._logger.debug(
            f"Executing RPC call on NerdDiary server. Method <{method}> with <{mask_sensitive('params ' + str(params))}>. Assigned JSON RPC id: {str(id)}"
        )
        self._rpc_calls[id] = AsyncRPCResult(id=id)

        has_sent = False
        while not has_sent and self._running:
            try:
                await self._ws.send(json.dumps(req))
                has_sent = True
            except ConnectionClosedOK:
                self._logger.debug("Server disconnected normally")
                if not await self._connect():
                    return
            except ConnectionClosedError:
                self._logger.debug("Server disconnected with an error")
                if not await self._connect():
                    return
            except TimeoutError:
                self._logger.debug("Timeout while waiting for server send")
                if not await self._connect():
                    return
            except Exception:
                err = "Unexpected exception while sending rpc call."
                self._logger.exception(err)
                raise RuntimeError(err)

        try:
            self._logger.debug(
                f"Waiting for RPC call result. Method <{method}> with <{mask_sensitive('params ' + str(params))}>. Assigned JSON RPC id: {str(id)}"
            )
            res = await self._rpc_calls[id].get(timeout=self._config.rpc_call_timeout)
            self._logger.debug(f"RPC call result {mask_sensitive(str(res))}")
            return res
        except asyncio.CancelledError:
            self._logger.debug("Message dispatcher task cancelled")
        except NerdDiaryError:
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
            # Purge completed notification handler tasks
            to_remove = set()
            for task in self._notification_handler_tasks:
                if task.done():
                    to_remove.add(task)
            self._notification_handler_tasks -= to_remove

            try:
                raw_response = await self._ws.recv()
                self._logger.debug(f"Recieved message <{mask_sensitive(str(raw_response))}>")
                parsed_response = json.loads(raw_response)

                if "notification" in parsed_response:
                    # Process notification
                    try:
                        n_type = NotificationType(int(parsed_response["notification"]))
                        self._logger.debug(f"Recieved <{n_type.name}> notification. Scheduling processing")
                        self._notification_handler_tasks.add(
                            asyncio.create_task(self._process_notification(n_type, parsed_response["data"]))
                        )
                    except ValueError:
                        self._logger.debug(
                            f"Recieved unsupported notification <{parsed_response['notification']}>. Ignoring"
                        )
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

                            self._rpc_calls[id]._fut.set_exception(
                                NerdDiaryError(NerdDiaryErrorCode(code), message, data)
                            )
            except ConnectionClosedOK:
                self._logger.debug("Server disconnected normally")
                if not await self._connect():
                    break
            except ConnectionClosedError:
                self._logger.debug("Server disconnected with an error")
                if not await self._connect():
                    break
            except TimeoutError:
                self._logger.debug("Timeout while waiting for server response")
                if not await self._connect():
                    break
            except asyncio.CancelledError:
                self._logger.debug("Message dispatcher task cancelled")
                break
            except Exception:
                err = "Unexpected exception during message dispatching."
                self._logger.exception(err)
                break

        self._logger.debug("Exiting message dispatcher")

    def _stop(self):
        self._running = False

    async def _process_notification(self, n_type: NotificationType, raw_data: t.Dict[str, t.Any] | None = None):
        data = None
        if raw_data:
            data = self._parse_server_data(data=raw_data, context=f"Notification: {n_type.name}")

        # If this is a session update from the server, we need to store it and optionally unlock
        if n_type == NotificationType.SERVER_SESSION_UPDATE:
            if not isinstance(data, UserSessionSchema):
                self._logger.exception("Received incorrect session data from the server")
            else:
                user_id = data.user_id

                local_ses = self._sessions.get(user_id)
                if local_ses:
                    self._logger.debug("Found an existing session on client")
                    if (
                        data.user_status == UserSessionStatus.LOCKED
                        and local_ses.user_status > UserSessionStatus.LOCKED
                    ):
                        self._logger.debug("Client has unlocked session, while server is not - unlocking")
                        await self._run_rpc("unlock_session", params={"user_id": user_id, "key": local_ses.key})
                    else:
                        self._sessions[user_id] = data
                else:
                    self._sessions[user_id] = data

        for handler in self._notification_handlers[n_type]:
            try:
                await handler(n_type, data)
            except StopNotificationPropagation:
                pass
            except Exception:
                self._logger.exception("Exception during notification handling")

    async def get_session(self, user_id: str) -> UserSessionSchema | None:
        assert isinstance(user_id, str)
        local_ses = self._sessions.get(user_id)

        if not local_ses:
            try:
                local_ses = await self.exec_api_method("get_session", user_id=str(user_id))
                if not isinstance(local_ses, UserSessionSchema):
                    self._logger.exception("Received incorrect session data from the server")
                    return None

                self._sessions[user_id] = local_ses
            except ValidationError:
                self._logger.exception("Received incorrect session data from the server")
            except NerdDiaryError:
                pass

        return self._sessions[user_id]

    async def exec_api_method(self, method: str, **params) -> Schema | bool | None:
        try:
            res = await self._run_rpc(method=method, params=params)

            if res is None:
                err = f"{method} call timed out"
                self._logger.warning(err)
                return None

            if isinstance(res, bool):
                return res

            return self._parse_server_data(data=res, context=f"RPC method {method}")

        except NerdDiaryError as r_err:
            if r_err.code > NerdDiaryErrorCode.RPC_SERVER_ERROR:
                raise
            else:
                err = f"Unexpected RPCError during execution of remote {method=}"
                self._logger.exception(err)
                return None
        except Exception:
            err = f"Unexpected exception during execution of remote {method=}"
            self._logger.exception(err)
            return None

    def _parse_server_data(self, data: t.Dict[str, t.Any], context: str = "") -> Schema | None:
        def __all_subclasses(cls):
            return set(cls.__subclasses__()).union([s for c in cls.__subclasses__() for s in __all_subclasses(c)])

        if "schema" not in data or "data" not in data:
            err = f"Incorrect data from the server: 'schema' or 'data' keys are missing. {context=}"
            self._logger.error(err)
            return None

        schema_cls = None
        for cls in __all_subclasses(Schema):
            if cls.__name__ == data["schema"]:
                schema_cls = cls
                break

        if schema_cls is None:
            err = f"Schema class {data['schema']} doesn't exist. Returned by remote {context=}"
            self._logger.error(err)
            return None

        try:
            return schema_cls.parse_obj(data["data"])
        except ValidationError:
            err = f"Incorrect data (can't parse schema). Returned by remote {context=}"
            self._logger.exception(err)
            return None
