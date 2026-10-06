# `client/network.py`

## 측정 요청

`_serve`는 `load`와 `metrics`에 각각 하나의 task 슬롯을 두고 같은 종류의 중복 요청을 거부한다. `_dispatch`는 인증 확인 뒤 `ApiClientPort.get_load/get_metrics` 결과를 `Result(kind='load'/'metrics', player=검증된 값)`으로 queue에 넣는다. 실패는 전용 `*_error`로 보내고 302/401은 기존 로그인 만료 흐름에 맡긴다. 종료 시 두 task도 취소·회수한다.

## 책임과 경계

하나의 worker thread와 asyncio event loop를 소유하고 네트워크 유스케이스와 동시 task를 조정한다. `NetworkPort`를 구조적으로 구현하지만 인증·HTTP API·WebSocket·광고·응답 검증의 구체 구현은 알지 않는다. 해당 기능은 composition root가 주입한 factory와 port로만 호출한다.

직접 호출하는 계약:

- `AuthFactoryPort` / `AuthPort`
- `ApiClientFactoryPort` / `ApiClientPort`
- `GameSocketFactoryPort` / `GameSocketPort`
- `AdsClientFactoryPort` / `AdsClientPort`
- `ResponseValidatorPort`
- `messages.Request`, `messages.Result`

`network_auth`, `network_api`, `network_ws`, `network_ads`, `network_validation` concrete 모듈을 import하지 않는다.

## `NetworkWorker` 필드

- `origin`: `Config.server_base_url`에서 온 HTTP(S) origin.
- `ads_origin`: `Config.ads_base_url`에서 온 광고 origin.
- `_ads_factory`: 선택적인 `AdsClientFactoryPort`; None이면 공개 session/task를 만들지 않는다.
- `requests`, `results`: worker 내부 Queue. 상위 계층은 `submit`과 `get_result_nowait`으로만 접근한다.
- `thread`: `_run`을 실행하는 non-daemon `village-network` thread. 상위 계층은 `start`, `is_alive`, `join`으로만 접근한다.
- `_auth_factory`: `AuthFactoryPort`.
- `_api_factory`: `ApiClientFactoryPort`.
- `_game_socket_factory`: `GameSocketFactoryPort`.
- `_validator`: `ResponseValidatorPort`.
- `_authenticated`: worker 유스케이스의 현재 인증 여부.

## 공개 메서드

### `NetworkWorker.__init__(self, origin: str, auth_factory: AuthFactoryPort, api_factory: ApiClientFactoryPort, game_socket_factory: GameSocketFactoryPort, validator: ResponseValidatorPort, ads_origin: str = 'http://127.0.0.1:8001', ads_factory: AdsClientFactoryPort | None = None) -> None`

```text
게임/광고 origin과 주입받은 추상 factory/validator 저장
입출력 Queue 생성
target=_run인 worker Thread 생성
인증 상태 False
```

### `start(self) -> None`

```text
내부 thread.start()
```

### `submit(self, request: Request) -> None`

```text
내부 requests queue에 request를 대기 없이 추가
```

### `stop(self) -> None`

```text
submit(Request('stop'))
```

### `get_result_nowait(self) -> Result`

```text
내부 results queue에서 대기 없이 다음 Result 반환
비어 있으면 queue.Empty 전달
```

### `is_alive(self) -> bool`

```text
내부 thread.is_alive() 반환
```

### `join(self) -> None`

```text
종료된 내부 thread 회수
```

## worker 수명주기

### `_run(self) -> None`

```text
asyncio.run(_serve())
예상 밖 예외면 상세정보 없이 Result('fatal') 출력
finally 대기 Request를 모두 제거하면서 username/password 삭제
```

### `_serve(self) -> None` (`async`)

```text
로컬 IP cookie 허용 CookieJar와 기존 timeout 생성
trust_env=False인 게임 인증 ClientSession 생성
ads_factory가 있으면 AsyncExitStack에서 DummyCookieJar·5초 timeout·trust_env=False 공개 ClientSession 생성

AuthFactoryPort(session, origin) -> AuthPort
ApiClientFactoryPort(session, origin, validator, result sink) -> ApiClientPort
GameSocketFactoryPort(session, origin, validator, result sink) -> GameSocketPort
ads_factory가 있으면 AdsClientFactoryPort(public_session, ads_origin, result sink, game_session=session, game_origin=origin) -> AdsClientPort

ads_tasks(slot_id별), active, delivery_task, analytics_task, ingest_task, windows_task, history_task 슬롯과 load/metrics task 두 슬롯 유지
반복:
    완료 task await 후 슬롯 비우기
    request가 없으면 worker만 0.02초 yield
    stop이면 종료
    ads이면:
        AdsClientPort가 있고 request.slot_id의 task가 비면 select(request.request_id, request.slot_id)를 task로 시작; 중복 오류에도 slot_id 전달
        그 외 request_id가 포함된 ads_error 결과 반환
        일반 _dispatch/active 슬롯으로 전달하지 않음
    delivery/analytics/ingest/windows/history/load/metrics는 종류별 task 한 개만 허용
    windows 중복 요청은 windows_error로 반환
    일반 active는 한 개만 허용
    active 중 command가 오면 command_error 출력
    처리하지 않은 request credential 제거
finally:
    ads_tasks의 모든 슬롯을 포함한 남은 task 취소 및 회수
    GameSocketPort.shutdown()
    AuthPort.clear()
    공개 session의 AsyncExitStack 종료 후 게임 ClientSession context 종료
```

단일 thread·event loop와 게임 인증 HTTP/WS의 단일 ClientSession 원칙은 분리 전과 같다. 광고는 아래의 별도 무인증 session 계약을 따른다.

## 요청 조정

### `_dispatch(self, request: Request, auth: AuthPort, api: ApiClientPort, game_socket: GameSocketPort) -> None` (`async`)

```text
login:
    AuthPort.clear(), 인증 False
    request credential을 지역 변수로 옮기고 즉시 제거
    AuthPort.login(username, password)
    인증 True
    ApiClientPort.get_player()
    GameSocketPort.connect(expected player_id)
    Result('player') 출력
    GameSocketPort.start_listener()

player -> 인증 검사, ApiClientPort.get_player(), Result('player')
delivery -> 인증 검사, ApiClientPort.get_delivery(), Result('delivery')
analytics -> 인증 검사, ApiClientPort.get_analytics(), Result('analytics')
ingest -> 인증 검사, ApiClientPort.get_ingest(), Result('ingest')
windows -> 인증 검사, ApiClientPort.get_windows(), Result('windows', player=검증된 요약)
history -> 인증 검사, ApiClientPort.get_history(), Result('history')
load/metrics -> 인증 검사, ApiClientPort.get_load/get_metrics(), 각 Result 출력
logout -> GameSocketPort.close(), AuthPort.logout(), AuthPort.clear(), Result('logged_out')
command -> GameSocketPort.command(action, direction), Result('command')
           train 성공이면 Request('history')를 내부 queue에 추가

알려진 안전 오류:
    needs_login과 요청 종류에 따라 socket/auth 정리
    요청 종류별 *_error 또는 error Result 출력
finally:
    request username/password 제거
```

## 보존되는 조정 규칙

- UI thread는 네트워크를 기다리지 않는다.
- 로그인·명령·갱신·로그아웃은 일반 active 슬롯을 공유한다.
- delivery, analytics, ingest, windows, history, load, metrics는 각각 독립 task 하나를 허용한다.
- ingest는 사용자가 누른 재조회에만 실행되며 이미 게시된 결과를 GET으로 읽고 Spark/Kafka 연결을 만들지 않는다.
- windows는 같은 인증 session의 API port로 이미 게시된 시간 창 요약을 읽는다. 검증된 결과는 thread-safe 결과 queue에 `windows`로 전달하고 실패는 `windows_error`로 전달한다. 302/401은 기존 로그인 필요 오류 처리에 따른다.
- 종료 시 windows task도 다른 진행 중 요청과 함께 취소·회수한 다음 socket 종료, 인증 정리, session 종료 순서를 따른다.
- 수련 성공 뒤 history 요청을 자동 제출한다.
- 모든 외부 응답은 검증된 `Result`로만 상위 계층에 전달한다.
- replay 요청이나 task는 없다.

## 광고 경계

게임 인증 HTTP·WS는 같은 CookieJar(unsafe=True) session을 공유한다. 광고 선택에는 게임 session과 게임 origin을, 이미지 다운로드에는 별도 공개 session과 광고 origin을 주입한다. 게임 쿠키는 광고 서버로 전달하지 않는다. 선택·다운로드 제한과 결과 값은 [network_ads.py](network_ads.py.md)가 소유한다.
