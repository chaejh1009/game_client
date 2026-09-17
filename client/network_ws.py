"""WebSocket connection, broadcasts, and command acknowledgement matching."""
import asyncio
import time
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
import uuid

import aiohttp

from messages import Result
from network_errors import Failure
from ports import ResponseValidatorPort


class GameSocketClient:
    def __init__(self, session: aiohttp.ClientSession, origin: str,
                 validator: ResponseValidatorPort,
                 result_sink: Callable[[Result], None]):
        self._session = session
        self._origin = origin
        self._validator = validator
        self._result_sink = result_sink
        self._ws = None
        self._reader = None
        self._command_waiter = None
        self._command_id = None
        self._player_id = None
        self._last_command_at = -1.0

    async def close(self) -> None:
        reader = self._reader
        self._reader = None
        if reader is not None and reader is not asyncio.current_task():
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        if self._ws is not None:
            try:
                async with asyncio.timeout(1):
                    await self._ws.close()
            finally:
                self._ws = None
        self._player_id = None

    async def shutdown(self) -> None:
        await self.close()
        self._last_command_at = -1.0

    async def _receive_initial_state(self) -> tuple[dict, dict]:
        try:
            async with asyncio.timeout(2):
                message = await self._ws.receive()
        except TimeoutError:
            raise Failure('게임 연결 초기 상태 응답 시간이 초과되었습니다.') from None
        data = self._validator.decode_ws_message(message, self._ws.close_code)
        if data.get('type') == 'error':
            raise self._validator.command_failure(data)
        player = self._validator.validate_player(data)
        return player, self._validator.safe_state_message(player, data.get('command_id'))

    async def connect(self, expected_player_id: int | str) -> tuple[dict, dict]:
        parts = urlsplit(self._origin)
        ws_url = urlunsplit(('wss' if parts.scheme == 'https' else 'ws', parts.netloc,
                             '/ws/play/', '', ''))
        self._ws = await self._session.ws_connect(
            ws_url, origin=self._origin, max_msg_size=65536)
        player, safe = await self._receive_initial_state()
        if player['player_id'] != expected_player_id:
            raise Failure('HTTP와 게임 연결의 player가 일치하지 않습니다.')
        self._player_id = player['player_id']
        return player, safe

    def start_listener(self) -> None:
        self._reader = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        try:
            async for message in self._ws:
                data = self._validator.decode_ws_message(message, self._ws.close_code)
                kind = data.get('type')
                if kind == 'snapshot':
                    players = self._validator.validate_snapshot(data)
                    safe = {'type': 'snapshot', 'players': list(players)}
                    self._result_sink(Result('snapshot', players=players, ws_json=safe))
                    continue
                command_id = data.get('command_id')
                if kind == 'error':
                    self._result_sink(Result(
                        'ws_event', ws_json=self._validator.safe_error_message(data)))
                    if command_id == self._command_id and self._command_waiter is not None:
                        if not self._command_waiter.done():
                            self._command_waiter.set_exception(
                                self._validator.command_failure(data))
                    continue
                player = self._validator.validate_player(data)
                safe = self._validator.safe_state_message(player, command_id)
                if player['player_id'] != self._player_id:
                    self._result_sink(Result('state', player=player, ws_json=safe))
                    continue
                waiter_pending = (self._command_waiter is not None
                                  and not self._command_waiter.done())
                if waiter_pending:
                    self._result_sink(Result('ws_event', ws_json=safe))
                    if command_id == self._command_id:
                        self._command_waiter.set_result(player)
                    continue
                self._result_sink(Result('state', player=player, ws_json=safe))
        except asyncio.CancelledError:
            raise
        except (Failure, aiohttp.ClientError, ValueError) as error:
            failure = error if isinstance(error, Failure) else Failure('게임 연결이 종료되었습니다.')
            if self._command_waiter is not None and not self._command_waiter.done():
                self._command_waiter.set_exception(failure)
            else:
                self._result_sink(Result(
                    'error', str(failure), needs_login=failure.needs_login))
        finally:
            if self._command_waiter is not None and not self._command_waiter.done():
                self._command_waiter.set_exception(Failure('게임 연결이 종료되었습니다.'))
            if self._reader is asyncio.current_task():
                self._result_sink(Result(
                    'ws_disconnected',
                    '게임 연결이 끊겼습니다. 온라인 정보는 마지막 수신 상태입니다.'))

    async def command(self, action: str, direction: str) -> dict:
        if self._ws is None or self._ws.closed:
            raise Failure('게임 연결이 끊어졌습니다. 다시 로그인하세요.', True)
        if action not in ('move', 'gather', 'train'):
            raise Failure('올바르지 않은 게임 명령입니다.')
        now = time.monotonic()
        if self._last_command_at >= 0 and now - self._last_command_at < 0.2:
            raise Failure('게임 명령은 모두 합쳐 초당 최대 5개입니다.')
        self._last_command_at = now
        command_id = str(uuid.uuid4())
        payload = {'type': action, 'command_id': command_id}
        if action == 'move':
            payload['direction'] = direction
        self._command_id = command_id
        self._command_waiter = asyncio.get_running_loop().create_future()
        try:
            await self._ws.send_json(payload)
            async with asyncio.timeout(2):
                return await self._command_waiter
        except TimeoutError:
            raise Failure('게임 명령 응답 시간이 초과되었습니다.') from None
        finally:
            self._command_waiter = None
            self._command_id = None
