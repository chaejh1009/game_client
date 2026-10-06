# `client/network_ads.py`

## 책임과 경계

게시판은 게임 인증 session/game_origin, 로그인창 로비는 무인증 session/game_origin으로 광고를 선택하고, 별도의 무인증 DummyCookieJar session/광고 origin으로 공개 이미지를 받는다. pygame이나 광고 서버 매체 키를 다루지 않는다.

## 함수

- `creative_path(value) -> str`: 512자 이하 ASCII `/static/ads/creatives/` 경로만 허용한다. 외부 origin, query, fragment, percent encoding, 경로 순회, 백슬래시, 빈 segment와 `.`을 거부한다.
- `validate_decision(data, slot_id='village-board') -> dict`: empty=true 또는 ad=null은 요청 슬롯의 빈 결과로 정규화한다. 선택 결과의 식별자·title·요청 slot_id·비음수 정수 bid_units(또는 bid_amount)를 검사한다. body는 4000자 이하 문자열이며 줄바꿈·탭을 허용한다. creative_path는 다운로드용으로 보존하다 queue 전 제거한다.

## `AdsClient`

- `__init__`: 공개 이미지 session/origin, 게임 인증 session/origin, 결과 sink를 저장한다.
- `_read(response, limit)`: Content-Length와 누적 청크 모두 상한을 적용한다.
- `_decision(slot_id)`: 게임 GET `/api/ads/decision/?slot_id=...`을 먼저 요청한다. 로비는 DummyCookieJar session으로 조회하며 405이면 로그인 전 조회 미지원 안내로 끝낸다. 게시판은 405일 때만 현재 게임 cookie jar의 csrftoken으로 JSON POST `{slot_id}`를 재요청한다. X-CSRFToken·Origin·Referer는 게임 origin에만 보낸다. 토큰이 없으면 재로그인 안내로 끝낸다. redirect는 따라가지 않는다.
- `_parse_decision(response, slot_id)`: 200/JSON/64KiB 응답을 검증한다. 302/401은 게시판 재로그인 또는 로비 로그인 전 조회 불허 안내, 403은 CSRF 인증, 404는 API 설정, 503은 광고 서버 연결·매체 인증 확인 안내, 다른 비200은 HTTP 상태를 안내한다.
- `select(request_id, slot_id='village-board')`: village-board/lobby-banner만 허용한다. ads_decision 출력 후 empty이면 끝낸다. creative_path 없이 body가 있으면 ads_text를 출력한다. 그 외 공개 경로에서 5초 제한으로 이미지를 GET해 200/PNG·JPEG·WebP·GIF MIME/2MiB/비어 있지 않음을 확인하고 ads_image를 출력한다. 모든 결과에 slot_id/request_id/decision_id를 전달한다. 예상 오류는 ads_error 또는 ads_image_error로 출력하며 원문 통신 오류를 노출하지 않는다.

공개 이미지 요청은 쿠키·CSRF·매체 키·Origin·Authorization을 보내지 않고 redirect를 따르지 않는다. session 수명과 task 취소는 [network.py](network.py.md)가 소유한다.
