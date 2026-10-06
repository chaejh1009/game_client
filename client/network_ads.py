"""Game-authenticated ad selection and credential-free creative downloads."""
import json
import re
from urllib.parse import urlsplit

import aiohttp

from messages import Result
from network_errors import Failure


IMAGE_LIMIT = 2 * 1024 * 1024
IMAGE_MIMES = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}


def creative_path(value: object) -> str:
    # A strict ASCII path also rejects encoded traversal/separators and URL controls.
    if not isinstance(value, str) or len(value) > 512:
        raise Failure('광고 이미지 경로를 사용할 수 없습니다.')
    url = urlsplit(value)
    if (url.scheme or url.netloc or url.query or url.fragment
            or not re.fullmatch(r'/static/ads/creatives/[A-Za-z0-9_./-]+', value)
            or '..' in value or '\\' in value
            or any(part in ('', '.') for part in value.split('/')[1:])):
        raise Failure('광고 이미지 경로를 사용할 수 없습니다.')
    return value


def validate_decision(data: object) -> dict:
    if not isinstance(data, dict) or type(data.get('empty')) is not bool:
        raise Failure('광고 선택 응답을 확인할 수 없습니다.')
    if data['empty']:
        return {'empty': True, 'slot_id': 'village-board'}
    safe = {'empty': False}
    for key in ('decision_id', 'campaign_id', 'policy_version'):
        value = data.get(key)
        if (type(value) not in (str, int) or not str(value)
                or len(str(value)) > 128 or not str(value).isprintable()):
            raise Failure('광고 선택 응답을 확인할 수 없습니다.')
        safe[key] = value
    title = data.get('title')
    if not isinstance(title, str) or not title or len(title) > 240 or not title.isprintable():
        raise Failure('광고 제목을 확인할 수 없습니다.')
    if data.get('slot_id') != 'village-board' or type(data.get('bid_units')) is not int or data['bid_units'] < 0:
        raise Failure('광고 슬롯·포인트를 확인할 수 없습니다.')
    safe.update(title=title, slot_id=data['slot_id'], bid_units=data['bid_units'])
    # Keep the valid title even when a creative path is rejected later.
    safe['creative_path'] = data.get('creative_path')
    return safe


class AdsClient:
    def __init__(self, session, origin: str, result_sink, *,
                 game_session, game_origin: str):
        self._session = session  # DummyCookieJar, no auth/default secret headers.
        self._origin = origin
        self._sink = result_sink
        self._game_session = game_session
        self._game_origin = game_origin

    async def _read(self, response, limit: int) -> bytes:
        if response.content_length is not None and response.content_length > limit:
            response.close()
            raise Failure('광고 응답의 크기 제한을 초과했습니다.')
        body = bytearray()
        async for chunk in response.content.iter_chunked(16384):
            if len(body) + len(chunk) > limit:
                response.close()
                raise Failure('광고 응답의 크기 제한을 초과했습니다.')
            body.extend(chunk)
        return bytes(body)

    async def select(self, request_id: int) -> None:
        decision_id = ''
        try:
            async with self._game_session.get(
                    self._game_origin + '/api/ads/decision/', params={'slot_id': 'village-board'},
                    allow_redirects=False, headers={'Accept': 'application/json'}) as response:
                if response.status in (302, 401):
                    raise Failure('광고 선택을 위해 게임에 다시 로그인하세요.')
                if response.status == 404:
                    raise Failure('게임 서버의 광고 선택 API 설정을 확인하세요.')
                if response.status != 200:
                    raise Failure(f'광고 선택 요청 실패 (HTTP {response.status}).')
                if response.content_type != 'application/json':
                    raise Failure('광고 선택 응답 형식을 확인하세요.')
                data = validate_decision(json.loads(await self._read(response, 65536)))
            decision_id = str(data.get('decision_id', ''))
            path_value = data.pop('creative_path', None)
            self._sink(Result('ads_decision', ad=data, request_id=request_id,
                              decision_id=decision_id))
            if data['empty']:
                return
            path = creative_path(path_value)
            async with self._session.get(
                    self._origin + path, allow_redirects=False,
                    headers={'Accept': ', '.join(sorted(IMAGE_MIMES))},
                    timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200 or response.content_type not in IMAGE_MIMES:
                    raise Failure('광고 이미지를 준비할 수 없습니다.')
                body = await self._read(response, IMAGE_LIMIT)
                if not body:
                    raise Failure('광고 이미지가 비어 있습니다.')
            self._sink(Result('ads_image', image_bytes=body, decision_id=decision_id,
                              request_id=request_id))
        except (Failure, aiohttp.ClientError, TimeoutError, ValueError, UnicodeError) as error:
            kind = 'ads_image_error' if decision_id else 'ads_error'
            message = (str(error) if isinstance(error, Failure) else
                       '광고 이미지 연결을 확인하세요.' if decision_id else
                       '게임 서버의 광고 선택 연결을 확인하세요.')
            self._sink(Result(kind, message,
                              decision_id=decision_id, request_id=request_id))
