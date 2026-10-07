"""Validated JSON API access over an injected aiohttp session."""
import json
from typing import Callable

import aiohttp
from yarl import URL

from messages import Result
from network_errors import Failure
from ports import ResponseValidatorPort


class AdEventRejected(Failure):
    """Permanent event rejection: choose a new ad instead of retrying this event."""
    event_rejected = True


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
            '/api/analytics/', self._validator.validate_analytics)

    async def get_ingest(self) -> dict:
        return await self._get(
            '/api/analytics/ingest/', self._validator.validate_ingest,
            '마지막 수집 통계를 읽을 수 없음')

    async def get_ingest_analytics(self) -> dict:
        return await self.get_ingest()

    async def get_windows(self) -> dict:
        return await self._get(
            '/api/analytics/windows/', self._validator.validate_windows)

    async def get_load(self) -> dict:
        return await self._get('/api/analytics/load/', self._validator.validate_load)

    async def get_metrics(self) -> dict:
        return await self._get('/api/analytics/metrics/', self._validator.validate_metrics)

    async def get_history(self) -> dict:
        return await self._get('/api/history/', self._validator.validate_history)

    async def post_ad_event(self, decision_id: str, event_type: str) -> dict:
        if (not isinstance(decision_id, str) or not decision_id
                or len(decision_id) > 128 or event_type not in ('impression', 'click')):
            raise Failure('광고 실적 요청을 확인하세요.')
        path = '/api/ads/events/'
        url = self._origin + path
        cookie = self._session.cookie_jar.filter_cookies(URL(url)).get('csrftoken')
        if cookie is None or not cookie.value:
            raise Failure('광고 실적을 저장하려면 게임에 다시 로그인하세요.', True)
        status = None
        safe = None
        try:
            async with self._session.post(
                    url, json={'decision_id': decision_id, 'event_type': event_type},
                    headers={'Accept': 'application/json', 'X-CSRFToken': cookie.value,
                             'Origin': self._origin, 'Referer': self._origin + '/play/'},
                    allow_redirects=False) as response:
                status = response.status
                if status in (302, 401):
                    raise AdEventRejected('광고 실적을 저장하려면 게임에 다시 로그인하세요.', True)
                if status in (400, 403, 404):
                    reasons = {400: '광고 사건이 거절되었습니다.',
                               403: '게임 CSRF 인증이 거절되었습니다.',
                               404: '게임 서버의 광고 사건 경로가 없습니다.'}
                    reason = reasons[status]
                    if status == 400 and response.content_type == 'application/json':
                        raw = await response.content.read(65536)
                        try:
                            error_body = json.loads(raw)
                        except (ValueError, UnicodeError):
                            error_body = {}
                        code = error_body.get('error') if isinstance(error_body, dict) else None
                        known = {
                            'decision_snapshot_missing': '기존 결정에 저장된 정보가 부족합니다.',
                            'decision_not_found_for_subject': '현재 수신자의 광고 결정이 아닙니다.',
                            'impression_required': '서버에서 선행 노출을 확인하지 못했습니다.',
                        }
                        reason = known.get(code, reason) if isinstance(code, str) else reason
                    raise AdEventRejected(f'{reason} 광고 새 요청 필요 (HTTP {status}).')
                if status != 200:
                    raise Failure(f'광고 실적 저장 실패 (HTTP {status}). 같은 결정을 다시 전송합니다.')
                if response.content_type != 'application/json':
                    raise Failure('광고 실적 응답은 JSON이어야 합니다.')
                body = bytearray()
                async for chunk in response.content.iter_chunked(8192):
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise Failure('광고 실적 응답이 너무 큽니다.')
                data = json.loads(body)
                if (not isinstance(data, dict)
                        or data.get('event_id') != decision_id + ':' + event_type
                        or data.get('event_type') != event_type
                        or type(data.get('created')) is not bool):
                    raise Failure('광고 실적 확인 응답을 확인하세요.')
                safe = {name: data[name] for name in ('event_id', 'event_type', 'created')}
                return safe
        finally:
            self._result_sink(Result('api', status=status, player=safe, api_path=path))
