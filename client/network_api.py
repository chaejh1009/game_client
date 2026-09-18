"""Validated JSON API access over an injected aiohttp session."""
import json
from typing import Callable

import aiohttp

from messages import Result
from network_errors import Failure
from ports import ResponseValidatorPort


class ApiClient:
    def __init__(self, session: aiohttp.ClientSession, origin: str,
                 validator: ResponseValidatorPort,
                 result_sink: Callable[[Result], None]):
        self._session = session
        self._origin = origin
        self._validator = validator
        self._result_sink = result_sink

    async def _get(self, path: str, validate: Callable[[dict], dict],
                   unavailable_message: str = '') -> dict:
        status = None
        safe = None
        try:
            async with self._session.get(
                    self._origin + path, headers={'Accept': 'application/json'},
                    allow_redirects=False) as response:
                status = response.status
                if status in (302, 401):
                    raise Failure('로그인이 필요합니다. 계정을 확인하고 다시 접속하세요.', True)
                if status == 403:
                    raise Failure('접속 거부: 서버의 CSRF / Origin 설정을 확인하세요.')
                if not 200 <= status < 300:
                    if status == 503 and unavailable_message:
                        raise Failure(unavailable_message)
                    raise Failure(f'서버 요청 실패 (HTTP {status}).')
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
                safe = validate(data)
                return safe
        finally:
            self._result_sink(Result('api', status=status, player=safe, api_path=path))

    async def get_player(self) -> dict:
        return await self._get('/api/player/', self._validator.validate_player)

    async def get_delivery(self) -> dict:
        return await self._get('/api/delivery/', self._validator.validate_delivery)

    async def get_analytics(self) -> dict:
        return await self._get(
            '/api/analytics/actions/', self._validator.validate_analytics)

    async def get_ingest(self) -> dict:
        return await self._get(
            '/api/analytics/ingest/', self._validator.validate_ingest,
            '마지막 수집 통계를 읽을 수 없음')

    async def get_ingest_analytics(self) -> dict:
        return await self.get_ingest()

    async def get_history(self) -> dict:
        return await self._get('/api/history/', self._validator.validate_history)
