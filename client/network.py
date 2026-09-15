"""One worker thread, one event loop, one in-memory aiohttp session.

No pygame, logging, cookie persistence, or generic URL dispatch here.
"""
import asyncio
import json
from queue import Empty, Queue
from threading import Thread
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
import aiohttp
from state import PLAYER_FIELDS, Request, Result

class Failure(Exception):
    def __init__(self, message, needs_login=False):
        super().__init__(message)
        self.needs_login = needs_login

class NetworkWorker:
    def __init__(self, origin):
        self.origin = origin
        self.requests = Queue()
        self.results = Queue()
        self.thread = Thread(target=self._run, name='village-network', daemon=False)
        self._token = ''
        self._authenticated = False
        self._ws = None  # The socket belongs exclusively to this worker's event loop.
        self._ws_reader = None
        self._command_waiter = None
        self._command_id = None
        self._player_id = None
        self._last_command_at = -1.0

    def start(self):
        self.thread.start()

    def submit(self, request):
        self.requests.put_nowait(request)

    def stop(self):
        self.submit(Request('stop'))

    def _run(self):
        try:
            asyncio.run(self._serve())
        except Exception:
            # Never forward raw exception strings, headers, bodies, or tracebacks.
            self.results.put(Result('fatal', '네트워크 worker가 종료되었습니다. 앱을 다시 실행하세요.'))
        finally:
            self._token = ''
            self._player_id = None
            while True:
                try:
                    request = self.requests.get_nowait()
                    request.password = request.username = ''
                except Empty:
                    break

    async def _serve(self):
        # unsafe=True is ONLY for cookies on the classroom's local IP server.
        jar = aiohttp.CookieJar(unsafe=True)
        timeout = aiohttp.ClientTimeout(total=4, connect=2, sock_read=2)
        async with aiohttp.ClientSession(cookie_jar=jar, timeout=timeout,
                                         trust_env=False) as self._session:
            active = None
            try:
                while True:
                    if active is not None and active.done():
                        await active
                        active = None
                    try:
                        request = self.requests.get_nowait()
                    except Empty:
                        await asyncio.sleep(0.02)  # Only the worker yields; UI never waits.
                        continue
                    if request.kind == 'stop':
                        break
                    if active is None:
                        active = asyncio.create_task(self._dispatch(request))
                    else:
                        if request.kind == 'command':
                            self.results.put(Result(
                                'command_error', '이전 게임 명령의 응답을 기다려 주세요.',
                                direction=request.direction, action=request.action))
                        request.password = request.username = ''
            finally:
                if active is not None:
                    active.cancel()
                    await asyncio.gather(active, return_exceptions=True)
                await self._close_ws()
                jar.clear()
                self._token = ''
                self._last_command_at = -1.0

    async def _close_ws(self):
        reader = self._ws_reader
        self._ws_reader = None
        if reader is not None and reader is not asyncio.current_task():
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        if self._ws is not None:
            try:
                async with asyncio.timeout(1):
                    await self._ws.close()
            finally:
                self._ws = None

    def _decode_ws_message(self, message):
        if message.type != aiohttp.WSMsgType.TEXT:
            needs_login = self._ws.close_code == 4401
            raise Failure('게임 연결이 종료되었습니다.', needs_login)
        if len(message.data) > 65536:
            raise Failure('게임 응답이 너무 큽니다.')
        try:
            data = json.loads(message.data)
        except (ValueError, UnicodeError):
            raise Failure('게임 응답 형식이 올바르지 않습니다.') from None
        if not isinstance(data, dict):
            raise Failure('게임 응답은 객체여야 합니다.')
        return data

    def _validate_snapshot(self, data):
        raw_players = data.get('players')
        if not isinstance(raw_players, list) or len(raw_players) > 100:
            raise Failure('게임 snapshot의 players 형식을 확인하세요.')
        players = tuple(self._validate_player(player) for player in raw_players)
        ids = [player['player_id'] for player in players]
        if len(ids) != len(set(ids)):
            raise Failure('게임 snapshot에 중복 player가 있습니다.')
        return players

    def _command_failure(self, data):
        messages = {
            'too_fast': '이동과 채굴 명령은 모두 합쳐 초당 최대 5개입니다.',
            'outside_map': '맵 바깥으로 이동할 수 없습니다.',
            'invalid_direction': '올바르지 않은 이동 방향입니다.',
            'not_at_gather_tile': '코인은 채굴 지점 (2, 2)에서만 채굴할 수 있습니다.',
            'unknown_action': '올바르지 않은 게임 명령입니다.',
        }
        return Failure(messages.get(data.get('code'), '게임 명령을 처리하지 못했습니다.'))

    async def _listen_ws(self):
        try:
            async for message in self._ws:
                data = self._decode_ws_message(message)
                kind = data.get('type')
                if kind == 'snapshot':
                    self.results.put(Result('snapshot', players=self._validate_snapshot(data)))
                    continue
                command_id = data.get('command_id')
                if kind == 'error':
                    if command_id == self._command_id and self._command_waiter is not None:
                        if not self._command_waiter.done():
                            self._command_waiter.set_exception(self._command_failure(data))
                    continue
                player = self._validate_player(data)
                self.results.put(Result('state', player=player))
                if command_id == self._command_id and self._command_waiter is not None:
                    if player['player_id'] != self._player_id:
                        if not self._command_waiter.done():
                            self._command_waiter.set_exception(
                                Failure('게임 명령 응답의 player가 일치하지 않습니다.'))
                    elif not self._command_waiter.done():
                        self._command_waiter.set_result(player)
        except asyncio.CancelledError:
            raise
        except (Failure, aiohttp.ClientError, ValueError) as error:
            failure = error if isinstance(error, Failure) else Failure('게임 연결이 종료되었습니다.')
            if self._command_waiter is not None and not self._command_waiter.done():
                self._command_waiter.set_exception(failure)
            else:
                self.results.put(Result('error', str(failure), needs_login=failure.needs_login))
        finally:
            if self._command_waiter is not None and not self._command_waiter.done():
                self._command_waiter.set_exception(Failure('게임 연결이 종료되었습니다.'))

    async def _http(self, method, path, *, payload=None, empty_ok=False):
        inspect_player = method == 'GET' and path == '/api/player/'
        status, safe = None, None
        headers = {'Accept': 'application/json'}
        if method == 'POST':
            headers.update({'X-CSRFToken': self._token, 'Origin': self.origin})
        try:
            async with self._session.request(method, self.origin + path, json=payload,
                    headers=headers, allow_redirects=False) as response:
                status = response.status
                if status in (302, 401):
                    raise Failure('로그인이 필요합니다. 계정을 확인하고 다시 접속하세요.', True)
                if status == 403:
                    raise Failure('접속 거부: 서버의 CSRF / Origin 설정을 확인하세요.')
                if not 200 <= status < 300:
                    raise Failure(f'서버 요청 실패 (HTTP {status}).')
                if empty_ok and status == 204:
                    return None
                if response.content_type != 'application/json' and not (
                        response.content_type.startswith('application/')
                        and response.content_type.endswith('+json')):
                    raise Failure('JSON 응답이 아닙니다. 서버 API 경로와 Content-Type을 확인하세요.')
                body = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise Failure('서버 JSON 응답이 너무 큽니다.')
                try:
                    data = json.loads(body)
                except (ValueError, UnicodeError):
                    raise Failure('서버 JSON 형식이 올바르지 않습니다.') from None
                if not isinstance(data, dict):
                    raise Failure('서버 JSON은 객체여야 합니다.')
                if inspect_player:
                    # A strict schema projection prevents arbitrary reflected secrets.
                    validated = {}
                    for key in PLAYER_FIELDS:
                        value = data.get(key)
                        if key in ('player_id', 'room_id'):
                            valid = type(value) is int or (isinstance(value, str) and len(value) <= 80)
                        else:
                            valid = type(value) is int
                        if not valid:
                            raise Failure('player 응답의 필수 필드 또는 자료형을 확인하세요.')
                        validated[key] = value
                    safe = validated
                    return safe
                return data
        finally:
            if inspect_player:
                self.results.put(Result('api', status=status, player=safe))

    def _validate_player(self, data):
        if not isinstance(data, dict):
            raise Failure('player 응답은 객체여야 합니다.')
        validated = {}
        for key in PLAYER_FIELDS:
            value = data.get(key)
            if key in ('player_id', 'room_id'):
                valid = type(value) is int or (isinstance(value, str) and len(value) <= 80)
            else:
                valid = type(value) is int
            if not valid:
                raise Failure('player 응답의 필수 필드 또는 자료형을 확인하세요.')
            validated[key] = value
        return validated

    async def _receive_initial_ws_state(self):
        try:
            async with asyncio.timeout(2):
                message = await self._ws.receive()
        except TimeoutError:
            raise Failure('게임 연결 초기 상태 응답 시간이 초과되었습니다.') from None
        data = self._decode_ws_message(message)
        if data.get('type') == 'error':
            raise self._command_failure(data)
        return self._validate_player(data)

    async def _connect_ws(self):
        parts = urlsplit(self.origin)
        ws_url = urlunsplit(('wss' if parts.scheme == 'https' else 'ws', parts.netloc,
                             '/ws/play/', '', ''))
        self._ws = await self._session.ws_connect(
            ws_url, origin=self.origin, max_msg_size=65536)
        return await self._receive_initial_ws_state()

    async def _command(self, action, direction):
        if self._ws is None or self._ws.closed:
            raise Failure('게임 연결이 끊어졌습니다. 다시 로그인하세요.', True)
        now = time.monotonic()
        if self._last_command_at >= 0 and now - self._last_command_at < 0.2:
            raise Failure('이동과 채굴 명령은 모두 합쳐 초당 최대 5개입니다.')
        self._last_command_at = now
        command_id = str(uuid4())
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

    async def _discard_html(self, response):
        size = 0
        async for chunk in response.content.iter_chunked(8192):
            size += len(chunk)
            if size > 65536:
                raise Failure('서버 HTML 응답이 너무 큽니다.')

    def _csrf_from_response(self, response):
        cookie = response.cookies.get('csrftoken')
        token = cookie.value if cookie is not None else ''
        if not token or len(token) > 512:
            raise Failure('Django 로그인 페이지에서 CSRF 쿠키를 받지 못했습니다.')
        self._token = token

    async def _prepare_form_login(self):
        async with self._session.get(
                self.origin + '/accounts/login/',
                headers={'Accept': 'text/html'}, allow_redirects=False) as response:
            if response.status == 404:
                raise Failure('Django 로그인 경로(/accounts/login/)를 찾을 수 없습니다.')
            if not 200 <= response.status < 300:
                raise Failure(f'로그인 페이지 요청 실패 (HTTP {response.status}).')
            await self._discard_html(response)
            self._csrf_from_response(response)

    async def _form_login(self, username, password):
        form = {'username': username, 'password': password}
        headers = {
            'Accept': 'text/html',
            'X-CSRFToken': self._token,
            'Origin': self.origin,
            'Referer': self.origin + '/accounts/login/',
        }
        try:
            async with self._session.post(
                    self.origin + '/accounts/login/', data=form, headers=headers,
                    allow_redirects=False) as response:
                if response.status == 403:
                    raise Failure('접속 거부: 서버의 CSRF / Origin 설정을 확인하세요.')
                if response.status in (301, 302, 303):
                    await self._discard_html(response)
                    self._csrf_from_response(response)  # Django rotates it after login().
                    return
                if response.status == 200:
                    await self._discard_html(response)
                    raise Failure('로그인에 실패했습니다. 계정을 확인하세요.', True)
                raise Failure(f'로그인 요청 실패 (HTTP {response.status}).')
        finally:
            form.clear()

    async def _form_logout(self):
        if not self._token:
            raise Failure('로그아웃에 사용할 CSRF 토큰이 없습니다.')
        headers = {
            'Accept': 'text/html',
            'X-CSRFToken': self._token,
            'Origin': self.origin,
            'Referer': self.origin + '/play/',
        }
        async with self._session.post(
                self.origin + '/accounts/logout/', data={}, headers=headers,
                allow_redirects=False) as response:
            if response.status == 403:
                raise Failure('접속 거부: 서버의 CSRF / Origin 설정을 확인하세요.')
            if response.status not in (200, 204, 301, 302, 303):
                raise Failure(f'로그아웃 요청 실패 (HTTP {response.status}).')
            await self._discard_html(response)

    async def _dispatch(self, request):
        try:
            if request.kind == 'login':
                self._session.cookie_jar.clear()
                self._token = ''
                self._authenticated = False
                await self._prepare_form_login()
                username, password = request.username, request.password
                request.password = request.username = ''
                try:
                    await self._form_login(username, password)
                finally:
                    username = password = ''
                self._authenticated = True
                player = await self._http('GET', '/api/player/')
                ws_player = await self._connect_ws()
                if ws_player['player_id'] != player['player_id']:
                    raise Failure('HTTP와 게임 연결의 player가 일치하지 않습니다.')
                player = ws_player
                self._player_id = player['player_id']
                self.results.put(Result('player', '마을 준비 중', player=player))
                self._ws_reader = asyncio.create_task(self._listen_ws())
            elif request.kind == 'player':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                player = await self._http('GET', '/api/player/')
                self.results.put(Result('player', '상태를 갱신했습니다.', player=player))
            elif request.kind == 'logout':
                try:
                    await self._close_ws()
                    await self._form_logout()
                finally:
                    self._session.cookie_jar.clear()
                    self._token = ''
                    self._authenticated = False
                    self._player_id = None
                self.results.put(Result('logged_out', '로그아웃했습니다.'))
            elif request.kind == 'command':
                player = await self._command(request.action, request.direction)
                message = ('코인 채굴을 완료했습니다.' if request.action == 'gather'
                           else '이동 명령을 완료했습니다.')
                self.results.put(Result(
                    'command', message, player=player, direction=request.direction,
                    action=request.action))
        except (Failure, aiohttp.ClientError, TimeoutError, ValueError) as error:
            message = str(error) if isinstance(error, Failure) else '서버 연결 실패 또는 시간 초과입니다. 다시 시도하세요.'
            needs_login = isinstance(error, Failure) and error.needs_login
            if request.kind in ('login', 'logout') or needs_login:
                self._session.cookie_jar.clear()
                self._token = ''
                self._authenticated = False
                self._player_id = None
                needs_login = True
            if request.kind == 'logout':
                message += ' 로컬 계정은 지웠으나 서버 로그아웃은 확인되지 않았습니다.'
            kind = 'command_error' if request.kind == 'command' else 'error'
            self.results.put(Result(kind, message, needs_login=needs_login,
                                    direction=request.direction, action=request.action))
        finally:
            request.password = request.username = ''
