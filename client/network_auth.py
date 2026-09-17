"""Django form authentication over an injected aiohttp session."""
import aiohttp

from network_errors import Failure


class DjangoAuth:
    def __init__(self, session: aiohttp.ClientSession, origin: str):
        self._session = session
        self._origin = origin
        self._token = ''

    def clear(self) -> None:
        self._session.cookie_jar.clear()
        self._token = ''

    async def _discard_html(self, response) -> None:
        size = 0
        async for chunk in response.content.iter_chunked(8192):
            size += len(chunk)
            if size > 65536:
                raise Failure('서버 HTML 응답이 너무 큽니다.')

    def _csrf_from_response(self, response) -> None:
        cookie = response.cookies.get('csrftoken')
        token = cookie.value if cookie is not None else ''
        if not token or len(token) > 512:
            raise Failure('Django 로그인 페이지에서 CSRF 쿠키를 받지 못했습니다.')
        self._token = token

    async def _prepare_login(self) -> None:
        async with self._session.get(
                self._origin + '/accounts/login/',
                headers={'Accept': 'text/html'}, allow_redirects=False) as response:
            if response.status == 404:
                raise Failure('Django 로그인 경로(/accounts/login/)를 찾을 수 없습니다.')
            if not 200 <= response.status < 300:
                raise Failure(f'로그인 페이지 요청 실패 (HTTP {response.status}).')
            await self._discard_html(response)
            self._csrf_from_response(response)

    async def login(self, username: str, password: str) -> None:
        await self._prepare_login()
        form = {'username': username, 'password': password}
        headers = {
            'Accept': 'text/html',
            'X-CSRFToken': self._token,
            'Origin': self._origin,
            'Referer': self._origin + '/accounts/login/',
        }
        try:
            async with self._session.post(
                    self._origin + '/accounts/login/', data=form, headers=headers,
                    allow_redirects=False) as response:
                if response.status == 403:
                    raise Failure('접속 거부: 서버의 CSRF / Origin 설정을 확인하세요.')
                if response.status in (301, 302, 303):
                    await self._discard_html(response)
                    self._csrf_from_response(response)
                    return
                if response.status == 200:
                    await self._discard_html(response)
                    raise Failure('로그인에 실패했습니다. 계정을 확인하세요.', True)
                raise Failure(f'로그인 요청 실패 (HTTP {response.status}).')
        finally:
            form.clear()

    async def logout(self) -> None:
        if not self._token:
            raise Failure('로그아웃에 사용할 CSRF 토큰이 없습니다.')
        headers = {
            'Accept': 'text/html',
            'X-CSRFToken': self._token,
            'Origin': self._origin,
            'Referer': self._origin + '/play/',
        }
        async with self._session.post(
                self._origin + '/accounts/logout/', data={}, headers=headers,
                allow_redirects=False) as response:
            if response.status == 403:
                raise Failure('접속 거부: 서버의 CSRF / Origin 설정을 확인하세요.')
            if response.status not in (200, 204, 301, 302, 303):
                raise Failure(f'로그아웃 요청 실패 (HTTP {response.status}).')
            await self._discard_html(response)
