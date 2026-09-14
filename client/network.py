"""One worker thread, one event loop, one in-memory aiohttp session.

No pygame, logging, cookie persistence, or generic URL dispatch here.
"""
import asyncio
import json
from queue import Empty, Queue
from threading import Thread
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
        self._ws = None  # HTTP-only milestone; any future WS must belong to this loop.

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
                        request.password = request.username = ''
            finally:
                if active is not None:
                    active.cancel()
                    await asyncio.gather(active, return_exceptions=True)
                await self._close_ws()
                jar.clear()
                self._token = ''

    async def _close_ws(self):
        if self._ws is not None:
            try:
                async with asyncio.timeout(1):
                    await self._ws.close()
            finally:
                self._ws = None

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
                self.results.put(Result('player', '마을 준비 중', player=player))
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
                self.results.put(Result('logged_out', '로그아웃했습니다.'))
        except (Failure, aiohttp.ClientError, TimeoutError, ValueError) as error:
            message = str(error) if isinstance(error, Failure) else '서버 연결 실패 또는 시간 초과입니다. 다시 시도하세요.'
            needs_login = isinstance(error, Failure) and error.needs_login
            if request.kind in ('login', 'logout') or needs_login:
                self._session.cookie_jar.clear()
                self._token = ''
                self._authenticated = False
                needs_login = True
            if request.kind == 'logout':
                message += ' 로컬 계정은 지웠으나 서버 로그아웃은 확인되지 않았습니다.'
            self.results.put(Result('error', message, needs_login=needs_login))
        finally:
            request.password = request.username = ''
