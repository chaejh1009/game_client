"""One worker thread, one event loop, one in-memory aiohttp session.

No pygame, logging, cookie persistence, or generic URL dispatch here.
"""
import asyncio
import json
from queue import Empty, Queue
from threading import Thread
import time
from urllib.parse import urlsplit, urlunsplit
import uuid
import aiohttp
from state import DELIVERY_FIELDS, PLAYER_FIELDS, Request, Result

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
            delivery_task = None
            analytics_task = None
            history_task = None
            try:
                while True:
                    if active is not None and active.done():
                        await active
                        active = None
                    if delivery_task is not None and delivery_task.done():
                        await delivery_task
                        delivery_task = None
                    if analytics_task is not None and analytics_task.done():
                        await analytics_task
                        analytics_task = None
                    if history_task is not None and history_task.done():
                        await history_task
                        history_task = None
                    try:
                        request = self.requests.get_nowait()
                    except Empty:
                        await asyncio.sleep(0.02)  # Only the worker yields; UI never waits.
                        continue
                    if request.kind == 'stop':
                        break
                    if request.kind == 'delivery':
                        if delivery_task is None:
                            delivery_task = asyncio.create_task(self._dispatch(request))
                        else:
                            self.results.put(Result(
                                'delivery_error', '이벤트 전달 상태 요청이 이미 진행 중입니다.'))
                        continue
                    if request.kind == 'analytics':
                        if analytics_task is None:
                            analytics_task = asyncio.create_task(self._dispatch(request))
                        else:
                            self.results.put(Result(
                                'analytics_error', '통계 읽기 요청이 이미 진행 중입니다.'))
                        continue
                    if request.kind == 'history':
                        if history_task is None:
                            history_task = asyncio.create_task(self._dispatch(request))
                        else:
                            self.results.put(Result(
                                'history_error', '행동 이력 요청이 이미 진행 중입니다.'))
                        continue
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
                if delivery_task is not None:
                    delivery_task.cancel()
                    await asyncio.gather(delivery_task, return_exceptions=True)
                if analytics_task is not None:
                    analytics_task.cancel()
                    await asyncio.gather(analytics_task, return_exceptions=True)
                if history_task is not None:
                    history_task.cancel()
                    await asyncio.gather(history_task, return_exceptions=True)
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

    def _safe_state_message(self, player, command_id=None):
        safe = {'type': 'state', **player}
        if isinstance(command_id, str) and len(command_id) <= 80:
            safe['command_id'] = command_id
        return safe

    def _safe_error_message(self, data):
        safe = {'type': 'error', 'code': str(data.get('code', 'unknown'))[:80]}
        command_id = data.get('command_id')
        if isinstance(command_id, str) and len(command_id) <= 80:
            safe['command_id'] = command_id
        return safe

    def _command_failure(self, data):
        messages = {
            'too_fast': '게임 명령은 모두 합쳐 초당 최대 5개입니다.',
            'outside_map': '맵 바깥으로 이동할 수 없습니다.',
            'invalid_direction': '올바르지 않은 이동 방향입니다.',
            'not_at_gather_tile': '코인은 채굴 지점 (2, 2)에서만 채굴할 수 있습니다.',
            'not_at_train_tile': '개인 수련은 수련 타일 (3, 2)에서만 가능합니다.',
            'unknown_action': '올바르지 않은 게임 명령입니다.',
        }
        return Failure(messages.get(data.get('code'), '게임 명령을 처리하지 못했습니다.'))

    async def _listen_ws(self):
        try:
            async for message in self._ws:
                data = self._decode_ws_message(message)
                kind = data.get('type')
                if kind == 'snapshot':
                    players = self._validate_snapshot(data)
                    safe = {'type': 'snapshot', 'players': list(players)}
                    self.results.put(Result('snapshot', players=players, ws_json=safe))
                    continue
                command_id = data.get('command_id')
                if kind == 'error':
                    self.results.put(Result('ws_event', ws_json=self._safe_error_message(data)))
                    if command_id == self._command_id and self._command_waiter is not None:
                        if not self._command_waiter.done():
                            self._command_waiter.set_exception(self._command_failure(data))
                    continue
                player = self._validate_player(data)
                safe = self._safe_state_message(player, command_id)
                if player['player_id'] != self._player_id:
                    # Another player's broadcast never acknowledges my command.
                    self.results.put(Result('state', player=player, ws_json=safe))
                    continue
                waiter_pending = (self._command_waiter is not None
                                  and not self._command_waiter.done())
                if waiter_pending:
                    # Keep the WS inspector current, but merge my player only after
                    # the matching command acknowledgement becomes a command result.
                    self.results.put(Result('ws_event', ws_json=safe))
                    if command_id == self._command_id:
                        self._command_waiter.set_result(player)
                    continue
                self.results.put(Result('state', player=player, ws_json=safe))
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
            if self._ws_reader is asyncio.current_task():
                self.results.put(Result('ws_disconnected',
                                        '게임 연결이 끊겼습니다. 온라인 정보는 마지막 수신 상태입니다.'))

    async def _http(self, method, path, *, payload=None, empty_ok=False):
        inspect_player = method == 'GET' and path == '/api/player/'
        inspect_delivery = method == 'GET' and path == '/api/delivery/'
        inspect_analytics = method == 'GET' and path == '/api/analytics/'
        inspect_history = method == 'GET' and path == '/api/history/'
        inspect_api = inspect_player or inspect_delivery or inspect_analytics or inspect_history
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
                if inspect_delivery:
                    source = data.get('source')
                    if not isinstance(source, str) or not source or len(source) > 80:
                        raise Failure('delivery 응답의 source를 확인하세요.')
                    validated = {'source': source}
                    for key in DELIVERY_FIELDS[1:]:
                        value = data.get(key)
                        if type(value) is not int or value < 0:
                            raise Failure('delivery 응답의 카운트 필드를 확인하세요.')
                        validated[key] = value
                    safe = validated
                    return safe
                if inspect_analytics:
                    available = data.get('available')
                    if type(available) is not bool:
                        raise Failure('analytics 응답의 available을 확인하세요.')
                    if not available:
                        safe = {'available': False}
                        return safe
                    schema_version = data.get('schema_version')
                    generated_at = data.get('generated_at')
                    event_count = data.get('event_count')
                    if type(schema_version) is not int or schema_version < 1:
                        raise Failure('analytics 응답의 schema_version을 확인하세요.')
                    if not isinstance(generated_at, str) or not generated_at or len(generated_at) > 120:
                        raise Failure('analytics 응답의 generated_at을 확인하세요.')
                    if type(event_count) is not int or event_count < 0:
                        raise Failure('analytics 응답의 event_count를 확인하세요.')
                    by_action = self._validate_analytics_rows(
                        data.get('by_action'), 'event_type', 'by_action')
                    by_room = self._validate_analytics_rows(
                        data.get('by_room'), 'room_id', 'by_room')
                    safe = {
                        'available': True,
                        'schema_version': schema_version,
                        'generated_at': generated_at,
                        'event_count': event_count,
                        'by_action': list(by_action),
                        'by_room': list(by_room),
                    }
                    return safe
                if inspect_history:
                    safe = self._validate_history(data)
                    return safe
                return data
        finally:
            if inspect_api:
                self.results.put(Result('api', status=status, player=safe, api_path=path))

    def _validate_analytics_rows(self, rows, label_key, field_name):
        if not isinstance(rows, list) or len(rows) > 100:
            raise Failure(f'analytics 응답의 {field_name} 형식을 확인하세요.')
        validated = []
        for row in rows:
            if not isinstance(row, dict):
                raise Failure(f'analytics 응답의 {field_name} 행을 확인하세요.')
            label = row.get(label_key)
            count = row.get('count')
            label_ok = (isinstance(label, str) and bool(label) and len(label) <= 80)
            if label_key == 'room_id':
                label_ok = label_ok or type(label) is int
            if not label_ok or type(count) is not int or count < 0:
                raise Failure(f'analytics 응답의 {field_name} 행을 확인하세요.')
            validated.append({label_key: label, 'count': count})
        return tuple(validated)

    def _validate_history(self, data):
        scope = data.get('scope')
        limit = data.get('limit')
        events = data.get('events')
        if scope != 'current-player':
            raise Failure('history 응답의 scope를 확인하세요.')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise Failure('history 응답의 limit을 확인하세요.')
        if not isinstance(events, list) or len(events) > limit:
            raise Failure('history 응답의 events 형식을 확인하세요.')
        validated_events = []
        for event in events:
            if not isinstance(event, dict):
                raise Failure('history 응답의 event 형식을 확인하세요.')
            schema_version = event.get('schema_version')
            event_id = event.get('event_id')
            event_type = event.get('event_type')
            player_id = event.get('player_id')
            room_id = event.get('room_id')
            event_time = event.get('event_time')
            payload = event.get('payload')
            if type(schema_version) is not int or schema_version < 1:
                raise Failure('history event의 schema_version을 확인하세요.')
            if not isinstance(event_id, str) or not event_id or len(event_id) > 80:
                raise Failure('history event의 event_id를 확인하세요.')
            if not isinstance(event_type, str) or not event_type or len(event_type) > 80:
                raise Failure('history event의 event_type을 확인하세요.')
            for name, value in (('player_id', player_id), ('room_id', room_id)):
                valid = type(value) is int or (
                    isinstance(value, str) and bool(value) and len(value) <= 80)
                if not valid:
                    raise Failure(f'history event의 {name}를 확인하세요.')
            if not isinstance(event_time, str) or not event_time or len(event_time) > 120:
                raise Failure('history event의 event_time을 확인하세요.')
            if not isinstance(payload, dict):
                raise Failure('history event의 payload를 확인하세요.')
            safe_payload = {}
            for key in ('x', 'y', 'coins', 'version'):
                value = payload.get(key)
                if type(value) is not int:
                    raise Failure(f'history event payload의 {key}를 확인하세요.')
                safe_payload[key] = value
            transition = payload.get('transition')
            safe_transition = None
            if transition is not None:
                if not isinstance(transition, dict):
                    raise Failure('history event payload의 transition을 확인하세요.')
                step = transition.get('step')
                reward = transition.get('reward')
                if type(step) is not int or step < 1:
                    raise Failure('history transition의 step을 확인하세요.')
                if isinstance(reward, bool) or not isinstance(reward, (int, float)):
                    raise Failure('history transition의 reward를 확인하세요.')
                safe_transition = {'step': step, 'reward': reward}
            safe_payload['transition'] = safe_transition
            validated_events.append({
                'schema_version': schema_version,
                'event_id': event_id,
                'event_type': event_type,
                'player_id': player_id,
                'room_id': room_id,
                'event_time': event_time,
                'payload': safe_payload,
            })
        return {'scope': scope, 'limit': limit, 'events': validated_events}

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
        player = self._validate_player(data)
        return player, self._safe_state_message(player, data.get('command_id'))

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
                ws_player, ws_json = await self._connect_ws()
                if ws_player['player_id'] != player['player_id']:
                    raise Failure('HTTP와 게임 연결의 player가 일치하지 않습니다.')
                player = ws_player
                self._player_id = player['player_id']
                self.results.put(Result('player', '마을 준비 중', player=player,
                                        ws_json=ws_json))
                self._ws_reader = asyncio.create_task(self._listen_ws())
            elif request.kind == 'player':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                player = await self._http('GET', '/api/player/')
                self.results.put(Result('player', '상태를 갱신했습니다.', player=player))
            elif request.kind == 'delivery':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                delivery = await self._http('GET', '/api/delivery/')
                self.results.put(Result('delivery', '이벤트 전달 상태를 갱신했습니다.',
                                        delivery=delivery))
            elif request.kind == 'analytics':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                analytics = await self._http('GET', '/api/analytics/')
                self.results.put(Result('analytics', '저장된 통계를 읽었습니다.',
                                        player=analytics))
            elif request.kind == 'history':
                if not self._authenticated:
                    raise Failure('먼저 로그인하세요.', True)
                history = await self._http('GET', '/api/history/')
                self.results.put(Result('history', '최근 행동 이력을 읽었습니다.',
                                        player=history))
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
                messages = {
                    'gather': '코인 채굴을 완료했습니다.',
                    'train': '개인 수련을 완료했습니다.',
                    'move': '이동 명령을 완료했습니다.',
                }
                self.results.put(Result(
                    'command', messages[request.action], player=player,
                    direction=request.direction,
                    action=request.action))
                if request.action == 'train':
                    # The worker loop runs this as an independent task using the
                    # same ClientSession, so gameplay input never waits on history.
                    self.requests.put_nowait(Request('history'))
        except (Failure, aiohttp.ClientError, TimeoutError, ValueError) as error:
            message = str(error) if isinstance(error, Failure) else '서버 연결 실패 또는 시간 초과입니다. 다시 시도하세요.'
            needs_login = isinstance(error, Failure) and error.needs_login
            if request.kind in ('login', 'logout') or needs_login:
                if needs_login:
                    await self._close_ws()
                self._session.cookie_jar.clear()
                self._token = ''
                self._authenticated = False
                self._player_id = None
                needs_login = True
            if request.kind == 'logout':
                message += ' 로컬 계정은 지웠으나 서버 로그아웃은 확인되지 않았습니다.'
            if request.kind == 'command':
                kind = 'command_error'
            elif request.kind == 'delivery':
                kind = 'delivery_error'
            elif request.kind == 'analytics':
                kind = 'analytics_error'
            elif request.kind == 'history':
                kind = 'history_error'
            else:
                kind = 'error'
            self.results.put(Result(kind, message, needs_login=needs_login,
                                    direction=request.direction, action=request.action))
        finally:
            request.password = request.username = ''
