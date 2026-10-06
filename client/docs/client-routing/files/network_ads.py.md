# `client/network_ads.py`

## 책임과 경계

게임 서버 게이트웨이를 통한 광고 선택과 제한된 static 이미지 bytes 다운로드를 소유한다. NetworkWorker가 같은 loop에서 만든 게임 인증 session/game_origin과 무인증 DummyCookieJar session/광고 origin/result sink를 주입한다. pygame, 로그인 절차, 광고주 로그인, GUI 상태를 알지 않는다. 직접 호출은 aiohttp GET, json.loads, urlsplit, messages.Result, network_errors.Failure다.

## 값·함수

- IMAGE_LIMIT=2097152, IMAGE_MIMES=PNG/JPEG/WebP/GIF의 MIME 집합.
- `creative_path(value) -> str`: 타입/512자 제한 -> urlsplit -> `/static/ads/creatives/` ASCII allowlist, host/scheme/query/fragment/`..`/백슬래시/percent encoding/빈 segment/`.` 거부 -> 경로 반환 또는 안전한 Failure.
- `validate_decision(data) -> dict`: dict와 bool empty 검사 -> empty이면 요청 슬롯의 빈 광고 -> false이면 decision_id/campaign_id/policy_version의 str/int·128자, title의 printable·240자, slot_id와 비음수 int bid_units 검사 -> 허용 값 반환. creative_path는 다운로드 검증에만 사용하고 queue 결과 전 제거한다.

## `AdsClient`

- `__init__(session, origin, result_sink, *, game_session, game_origin)`: 이미지용 공개 session/origin과 선택용 게임 session/origin, 결과 sink를 저장한다. 인증 세션이나 credential을 만들지 않는다.
- `_read(response, limit) -> await bytes`: Content-Length가 상한 초과면 close/Failure -> 16384 bytes 청크를 누적하기 전에 상한 검사 -> 초과 시 close/Failure -> bytes 반환. 길이 헤더가 없어도 동일하다.
- `select(request_id) -> await None`: 게임 인증 session으로 game_origin의 GET `/api/ads/decision/`에 slot_id=village-board, Accept JSON, redirect 금지 -> 200/JSON/64KiB 확인 -> validate_decision -> creative_path 원문 제거 후 ads_decision(request_id, decision_id, ad) 출력 -> empty이면 반환 -> creative_path 검사 -> 같은 공개 session에서 origin+경로 GET, redirect 금지, 5초 -> 200/허용 MIME/2MiB/비어 있지 않음 확인 -> ads_image(request_id, decision_id, image_bytes) 출력. 예상 오류는 원문 없이 ads_error 또는 ads_image_error로 보낸다. 302/401은 게임 재로그인, 404는 게임 API 설정, 다른 비200은 HTTP 상태, 비JSON은 응답 형식 안내 오류다. Failure의 안전한 안내는 유지하고 통신·파싱 오류 원문은 출력하지 않는다. POST는 없다.

공개 session은 default secret header가 없고 DummyCookieJar가 서버 Set-Cookie를 보관하지 않는다. 이미지에는 cookie/CSRF/매체 키/Origin/Authorization을 넣지 않는다. 종료·취소 시 response context가 닫히고 session 수명은 [network.py](network.py.md)가 관리한다.
