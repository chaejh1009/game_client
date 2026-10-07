# Client routing

이 문서는 `python client/main.py`로 실행되는 pygame 클라이언트의 탐색 진입점이다.
책임 분리와 행동 통계·Kafka 수집 통계·시간 창 표 작업이 기존 계약을 깨지 않도록 현재 호출 경계를 기록한다.

## 범위

라우팅 대상은 직접 유지보수하는 런타임 소스와 설정 파일이다. 각 대상은 `files/<client 상대경로>.md`와 정확히 하나씩 대응한다.

| 실제 파일 | 라우팅 문서 | 책임 |
|---|---|---|
| `client/main.py` | [`files/main.py.md`](files/main.py.md) | 설정 로드, 객체 조립, 프로세스 진입점 |
| `client/client_app.py` | [`files/client_app.py.md`](files/client_app.py.md) | pygame 수명주기, 이벤트·결과 루프, 60 FPS 유지와 스크롤 입력 |
| `client/controller.py` | [`files/controller.py.md`](files/controller.py.md) | 로그인·명령·조회·패널 유스케이스 조정 |
| `client/ports.py` | [`files/ports.py.md`](files/ports.py.md) | 계층 사이의 추상 호출 계약 |
| `client/messages.py` | [`files/messages.py.md`](files/messages.py.md) | 계층 사이의 요청·결과 값 계약 |
| `client/network.py` | [`files/network.py.md`](files/network.py.md) | worker 수명주기와 네트워크 유스케이스 조정 |
| `client/network_auth.py` | [`files/network_auth.py.md`](files/network_auth.py.md) | Django form/CSRF/cookie 인증 |
| `client/network_api.py` | [`files/network_api.py.md`](files/network_api.py.md) | 검증된 JSON API 조회와 CSRF 광고 사건 POST |
| `client/network_ws.py` | [`files/network_ws.py.md`](files/network_ws.py.md) | `/ws/play/`, broadcast, `command_id` 대기 |
| `client/network_validation.py` | [`files/network_validation.py.md`](files/network_validation.py.md) | HTTP/WS 응답 검증과 안전 투영 |
| `client/network_errors.py` | [`files/network_errors.py.md`](files/network_errors.py.md) | 네트워크 컴포넌트 공통 안전 오류 |
| `client/ads_panel.py` | [`files/ads_panel.py.md`](files/ads_panel.py.md) | 광고 결정·이미지·사건 확인 상태, 유지·갱신·재시도와 늦은 결과 거부 |
| `client/network_ads.py` | [`files/network_ads.py.md`](files/network_ads.py.md) | 게임 게이트웨이 광고 선택, 무인증·제한된 static 이미지 다운로드 |
| `client/render_ads.py` | [`files/render_ads.py.md`](files/render_ads.py.md) | 메인 스레드 광고 이미지 변환·출력과 확인 항목 |
| `client/panels.py` | [`files/panels.py.md`](files/panels.py.md) | 통계·이력 패널 상태 전이 |
| `client/render.py` | [`files/render.py.md`](files/render.py.md) | `RendererPort` façade와 장면 선택 |
| `client/render_support.py` | [`files/render_support.py.md`](files/render_support.py.md) | pygame 자산·글꼴·배치·공통 출력 |
| `client/render_login.py` | [`files/render_login.py.md`](files/render_login.py.md) | 로그인 장면 출력 |
| `client/render_game.py` | [`files/render_game.py.md`](files/render_game.py.md) | 인증 후 게임 장면 조정 |
| `client/render_world.py` | [`files/render_world.py.md`](files/render_world.py.md) | 마을 맵과 플레이어 출력 |
| `client/render_panels.py` | [`files/render_panels.py.md`](files/render_panels.py.md) | API·통계·이력 패널 출력 |
| `client/state.py` | [`files/state.py.md`](files/state.py.md) | 설정과 게임 UI 상태 |
| `client/config.json` | [`files/config.json.md`](files/config.json.md) | 실행 시 읽는 클라이언트 설정 값 |

`client/assets/**`는 렌더러가 소비하는 정적 바이너리/외부 배포 자산이므로 호출 라우팅 대상에서 제외한다. 실제로 참조되는 자산 경로는 `config.json.md`와 `render.py.md`에 기록한다. `.venv`, `__pycache__`, `.DS_Store` 같은 생성·로컬 파일도 제외한다.

## 계층별 호출 구조

```text
main.py : 구체 구현 생성 및 추상계약 타입으로 조립
  -> ApplicationPort.run()
     -> client_app.py : pygame 초기화, 사용자 이벤트와 worker 결과 소비
        -> ControllerPort -> controller.py
           -> StatePort -> state.py
           -> AnalyticsPanelPort/HistoryPanelPort -> panels.py
           -> AdsPanelPort -> ads_panel.py (게시판 사건 요청 상태)
           -> NetworkPort -> network.py
        -> AdsPanelPort -> ads_panel.py
        -> NetworkPort -> network.py
        -> RendererFactoryPort -> render.Renderer 생성
        -> RendererPort -> render.py
           -> render_ads.py : 게시판·로비별 광고 Rect와 독립 이미지 캐시, 확인 항목
           -> render_support.py : 자산, 배치, primitive
           -> render_login.py : 로그인 장면
           -> render_game.py : 게임 장면 조정
              -> render_world.py : 맵과 플레이어
              -> render_panels.py : API, 통계, 이력, 하단 측정 카드

client_app.py / controller.py / network.py / network_ads.py / ads_panel.py
  -> messages.py : Request/Result 값 계약

network.py
  -> AuthFactoryPort -> AuthPort -> network_auth.py
     -> /accounts/login/, /accounts/logout/
  -> ApiClientFactoryPort -> ApiClientPort -> network_api.py
     -> /api/player/, /api/delivery/, /api/analytics/, /api/analytics/ingest/
     -> /api/analytics/windows/, /api/analytics/load/, /api/analytics/metrics/, /api/history/
     -> POST /api/ads/events/ (게시판 노출·클릭)
  -> GameSocketFactoryPort -> GameSocketPort -> network_ws.py
     -> /ws/play/
  -> ResponseValidatorPort -> network_validation.py
  -> AdsClientFactoryPort -> AdsClientPort -> network_ads.py
     -> server_base_url + /api/ads/decision/?slot_id=village-board 또는 lobby-banner (게시판: 게임 인증 session/405이면 CSRF POST, 로비: 무인증 GET)
     -> ads_base_url + /static/ads/creatives/... (별도 무인증 session)
  -> Result 반환
```

각 계층은 다음 경계까지만 안다.

- `main.py`: 유일한 composition root로서 구체 구현을 생성하지만, 실행 호출은 `ApplicationPort` 계약을 따른다.
- `client_app.py`: `AdsPanelPort`, `ConfigPort`, `ControllerPort`, `NetworkPort`, `RendererFactoryPort`, `RendererPort`, 상태·패널 포트만 알고 구체 구현 모듈은 import하지 않는다.
- `controller.py`: `StatePort`, 통계·이력·광고 패널 포트, `NetworkPort`만 호출하며 pygame과 구체 구현은 모른다.
- `ports.py`: 상위 계층이 사용할 수 있는 속성과 메서드만 선언하고 구현과 I/O를 갖지 않는다.
- `messages.py`: `Request`, `Result`와 허용 필드 상수만 정의하며 상태나 I/O를 갖지 않는다.
- `network.py`: 요청 종류와 동시 task 정책만 알고 인증·API·WS·광고·검증 구현은 포트로 호출한다. 게임 HTTP/WS는 하나의 인증 session을 공유하고, 공개 광고용 DummyCookieJar session은 같은 worker loop에서 별도로 닫는다.
- `network_auth.py`: Django form/CSRF/cookie 계약만 안다.
- `network_api.py`: 기존 JSON endpoint와 부하·전달 측정 GET의 검증은 `ResponseValidatorPort`에 맡기며, 광고 사건 POST의 CSRF·상태 코드·응답 검증과 안전 투영은 직접 수행한다.
- `network_ws.py`: `/ws/play/`, broadcast, `command_id` waiter만 알고 응답 검증은 `ResponseValidatorPort`에 맡긴다.
- `network_validation.py`: 외부 데이터 검증과 안전 투영만 하며 네트워크 I/O를 하지 않는다.
- `network_errors.py`: 사용자에게 노출 가능한 메시지와 로그인 필요 여부만 보존한다.
- `state.py`: 허용된 행동과 결과 병합 규칙은 알지만 큐, HTTP, WS, pygame은 모른다.
- `panels.py`: 행동 집계·Kafka 수집·시간 창·부하 측정·전달 측정 snapshot·이력의 표시 상태와 관련 `Result.kind`만 알며 서버 호출 방식은 모른다. 시간 창의 종류 필터와 페이지 이동은 받은 배열에만 적용한다.
- `render.py`: `RendererPort` façade로서 장면을 선택하고 frame을 표시하며 창 크기·스크롤·입력 좌표 변환을 렌더 지원 계층에 전달한다. 광고가 실제 viewport에 보이는지 확인하고 blit 후 flip이 끝나면 AdsPanelPort.mark_displayed를 호출한다.
- `render_support.py`: 상태를 모르며 pygame 자산, 960px 가상 화면 배치, viewport와 hitbox 변환, 공통 출력을 소유한다.
- `render_login.py`, `render_game.py`, `render_world.py`, `render_panels.py`: 각자 맡은 장면을 포트 상태에서 읽어 출력하며 요청을 만들거나 상태를 변경하지 않는다.
- `config.json`: 값만 제공하며 호출 관계를 갖지 않는다.

## 추상계약 규칙

1. `main.py`만 구체 구현 클래스를 import하고 생성할 수 있다.
2. 상위 계층은 하위 구현 객체를 주입받되 `ports.py`의 Protocol 타입으로만 보관·호출한다.
3. `client_app.py`는 renderer, controller, network의 concrete 모듈을 import하지 않는다.
4. `controller.py`는 State, PanelState, NetworkWorker concrete 클래스를 import하지 않는다.
5. 네트워크 요청과 결과는 `messages.py` 값으로만 경계를 통과한다.
6. 구현체는 Protocol을 상속할 필요 없이 같은 signature를 제공하는 구조적 부분형 계약을 따른다.
7. `network.py`는 `network_ads`, `network_auth`, `network_api`, `network_ws`, `network_validation` concrete 모듈을 import하지 않는다.

## 반드시 유지할 기준선

- 실행 명령은 `python client/main.py`이다.
- 로그인은 Django form/CSRF/cookie 흐름을 유지한다.
- 게임 소켓은 `/ws/play/`를 사용한다.
- 방 `snapshot`과 개별 `state`를 모두 처리한다.
- 이동, 채집, 수련 명령을 유지한다.
- 자기 명령은 생성한 `command_id`와 일치하는 응답을 기다린 뒤 완료한다.
- 다른 플레이어 broadcast는 자기 명령 완료로 취급하지 않는다.
- 플레이어 병합은 `player_id`별 `version`이 낮은 상태로 되돌아가지 않는다.
- 최근 행동 이력 패널과 `/api/history/` 검사 기능을 유지한다.
- 통계 카드는 사용자가 열거나 `새로 읽기`를 누를 때 기존 worker의 인증 ClientSession으로 `GET /api/analytics/`를 한 번 읽는다. `available`, `schema_version`, `generated_at`, `source`, 선택적 `record_count`, `event_count`, `by_action`, `by_room`만 안전하게 투영한다. `raw`는 `DB 내보내기 스냅샷`, `delta`는 `event_id별 고유 사실 Delta`로 표시한다.
- 카드는 `event_count`를 `고유 확정 사실 수`, `record_count`를 `선택한 원천의 행 수`, `generated_at`을 `집계 생성 시각`으로 표시한다. `record_count`가 없으면 해당 항목을 숨긴다. `available=false`는 `아직 집계 없음`, 빈 그룹 배열은 `게시할 그룹 없음`으로 구분한다. 게임 플레이어의 좌표·coins·version에는 반영하지 않는다.
- Kafka 수집 통계는 사용자가 `통계 다시 읽기`를 눌렀을 때만 같은 ClientSession worker가 `GET /api/analytics/ingest/`로 이미 게시된 결과를 읽는다. Spark 실행이나 Kafka 연결은 만들지 않는다.
- 수집 통계 응답은 queue로 메인 스레드에 전달하고 Pygame 메인 스레드가 텍스트·Rect·Surface를 그린다. GUI 루프는 네트워크 대기·`time.sleep()`을 수행하지 않는다.
- 수집 통계가 없을 때 숫자 0을 합성하지 않으며, 503은 `마지막 수집 통계를 읽을 수 없음`, 302/401은 로그인 안내로 표시한다. 원문 `raw_value`·evidence 파일과 인증 정보는 접속기에 전달하거나 표시하지 않는다.
- 시간 창 `새로 읽기` 또는 API 응답 보기의 `windows` 버튼을 한 번 누르면 기존 인증 ClientSession worker가 `server_base_url + /api/analytics/windows/`를 GET한다. 요청과 결과는 thread-safe queue를 통과하며, Pygame 폰트·Rect·그리기는 메인 스레드에서 수행한다.
- 시간 창 표는 `확정 시간 창의 전달 레코드 수(중복 전달 포함 가능)`과 `시작 포함 · 끝 미포함 [window_start, window_end)`를 표시한다. `generated_at`은 집계 생성 시각이며 현재 게임의 `coords`·`coins`·`version`을 바꾸지 않는다.
- `available=false`는 `아직 창 요약 없음`, 게시 가능한 창 배열이 비면 `확정된 게시 대상 창 없음`으로 구분한다. `all`/`tumbling`/`sliding`과 5행 페이지는 받은 작은 배열을 화면에서 필터할 뿐 Spark 작업이나 서버 설정 변경을 요청하지 않는다.
- API 응답 보기는 player/history/windows/analytics/load/metrics GET의 경로·status·안전한 응답 JSON만 표시한다. `allow_redirects=False`, timeout, status/Content-Type 검사를 유지하며 HTML을 JSON으로 읽지 않고 auth·쿠키·CSRF를 표시하지 않는다.
- 기존 통계 탭의 game-summary 표, 온라인 상태, `village-board`/`lobby-banner` 광고용 두 Rect, `client/assets` 이미지와 한글 폰트를 유지한다. 접속기별 독립 인증 세션과 로그아웃·worker 종료·Pygame 종료 순서를 유지한다.
- 게임 아래 `최근 수업 측정`과 `분석 전달 상태` 카드는 각각 조회 버튼을 눌렀을 때만 기존 인증 ClientSession worker에서 `/api/analytics/load/`, `/api/analytics/metrics/`를 GET한다. 결과는 queue를 거쳐 메인 스레드의 기존 카드 내용을 교체한다. 창 폭 900px 미만에서는 두 카드를 세로로 배치하고 게임 영역 아래에 둔다.
- `available=false`는 `아직 측정 전`, null RTT는 `표본 없음`이다. 연결 수는 개, 처리율은 건/초, RTT는 ms로 표시한다. 부하 측정의 방별 표는 `room_id`/`connected`/`success_count`만 사용하며 DB 플레이어 수나 화면 캐릭터 수에서 측정값을 계산하지 않는다.
- 전달 카드에서는 `metrics.generated_at`과 `spark_progress.timestamp`를 별도로 표시하고 `kafka.lag_complete=false`이면 `일부 위치 미확인`을 붙인다. 조회 버튼은 저장된 결과만 읽으며 부하 측정이나 Spark 작업을 시작하지 않는다. 302/401은 기존 재로그인 흐름을 따르고 인증 원문을 기록하지 않는다.
- replay 기능과 replay 호출 경로는 만들지 않는다.
- 서버·Spark 코드와 기존 API/WS 계약은 변경 대상이 아니다.

## 문서 갱신 규칙

1. 런타임 소스나 설정 파일을 추가·이동·삭제하면 동일한 상대경로의 `.md`를 `files/` 아래에 함께 추가·이동·삭제한다.
2. 파일별 문서는 그 파일이 소유한 책임, 값, 함수/메서드, 바로 호출하는 외부 코드까지만 기술한다.
3. 함수 설명은 `signature -> guard/변환 -> 외부 호출 -> 반환/상태 변화` 순서의 의사코드로 적는다.
4. 다른 계층의 내부 구현은 중복 설명하지 않고 대응 문서로 링크한다.
5. 서버 계약이 달라 보이는 경우 클라이언트 문서만 임의로 바꾸지 말고 계약 변경 여부를 먼저 확인한다.

## 광고 선택·표시 계약

- 게임 화면의 게시판 슬롯과 로그인창 왼쪽의 로비 슬롯을 각 장면에서만 조회한다. 각 Rect가 완전히 보일 때만 요청하고 최소화/숨김·종료 중에는 멈춘다. 게시판은 통계·이력 overlay나 스크롤로 숨겨져도 멈춘다. 이동 입력과 FPS는 요청 계기가 아니다.
- `ads_base_url=http://127.0.0.1:8001`은 게임 origin과 별도 설정이다. 타일은 `client/assets`를 계속 사용하며 광고 creative는 서버 static에서만 읽는다.
- 광고 선택은 게임 origin의 GET `/api/ads/decision/?slot_id=...`를 요청한다. 게시판은 인증 session을 사용하며 405이면 CSRF JSON POST로 재요청한다. 로비는 무인증 GET만 사용하고 405/401이면 로그인 전 조회 미지원/불허 안내를 표시한다. empty=true는 `등록된 광고 없음`, false는 검증된 서버 title·creative를 표시한다. 이미지 광고와 body/bid_amount 본문 광고를 지원한다. 로그인 후 게시판의 실제 표시 완료 뒤 `/api/ads/events/`로 impression을 저장하고, 확인 완료 뒤 사용자 클릭을 click으로 저장한다. 로비에는 사건 POST를 보내지 않으며 로그인 전 노출 API 성공을 요구하지 않는다.
- 게시판 선택은 게임 인증 HTTP/WS session을 공유하며 로비 선택은 DummyCookieJar session을 사용한다. 이미지는 분리된 DummyCookieJar session으로 광고 origin에서 받으며 cookie, CSRF, 매체 키, Authorization을 보내지 않는다. 두 요청 모두 redirect를 따라가지 않는다.
- creative는 `/static/ads/creatives/` 아래 ASCII 경로만 허용한다. 외부 host/scheme, `..`, 역슬래시, percent encoding, query/fragment, 다른 경로를 거부한다. 이미지의 5초·200·PNG/JPEG/WebP/GIF MIME·2MiB 제한과 Content-Length 없는 청크 상한을 적용한다.
- queue의 이미지 결과는 요청 세대와 decision_id가 모두 현재 값일 때만 받는다. Surface는 메인 스레드에서 BytesIO→image.load→convert_alpha→blit하고 기존 present의 display.flip 후 표시 완료로 판정한다. 실패는 title 안내와 미표시 상태를 유지한다.
- 요청 시작 간격은 최소 15초, 결정 유지와 첫 성공 표시 이후 유지 시간은 각각 최소 10초다. 숨겨져 아직 변환되지 않은 bytes는 화면 복귀 후 표시 판정까지 갱신하지 않는다.
- 확인 항목은 결정 ID·캠페인·슬롯·모의 포인트·이미지 준비·표시 상태뿐이다. bid_units를 모의 포인트로 표시하며 게임 coins를 변경하지 않는다.
- 종료 시 광고 task도 취소·회수하고 무인증 session을 닫는다. 기존 게임 state/snapshot, command_id, 인증 세션과 로그아웃 순서는 그대로다.

- 게시판 사건 요청은 현재 request_id/decision_id/event_type으로 식별한다. 일시 실패는 최소 2초 뒤 같은 결정을 재전송하며 확인 전에는 광고를 교체하지 않는다. 400/403/404 영구 거절은 같은 사건을 멈추고 2초 뒤 새 광고를 요청한다. 사건 POST의 302/401과 CSRF cookie 부재는 기존 재로그인 흐름을 따른다. 광고 선택의 인증 오류는 광고 패널 안내로만 전달하며 게임 인증 상태를 초기화하지 않는다.
- 사건 task는 일반 게임 명령과 독립적으로 실행하고 종료 시 취소·회수한다. 로그아웃·인증 만료 시 두 광고 패널을 초기화하여 이전 결정 응답을 무효화한다.
