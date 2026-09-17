# `client/network.py`

## 책임과 경계

하나의 worker thread와 asyncio event loop를 소유하고 네트워크 유스케이스와 동시 task를 조정한다. `NetworkPort`를 구조적으로 구현하지만 인증·HTTP API·WebSocket·응답 검증의 구체 구현은 알지 않는다. 해당 기능은 composition root가 주입한 factory와 port로만 호출한다.

직접 호출하는 계약:

- `AuthFactoryPort` / `AuthPort`
- `ApiClientFactoryPort` / `ApiClientPort`
- `GameSocketFactoryPort` / `GameSocketPort`
- `ResponseValidatorPort`
- `messages.Request`, `messages.Result`

`network_auth`, `network_api`, `network_ws`, `network_validation` concrete 모듈을 import하지 않는다.

## `NetworkWorker` 필드

- `origin`: `Config.server_base_url`에서 온 HTTP(S) origin.
- `requests`, `results`: worker 내부 Queue. 상위 계층은 `submit`과 `get_result_nowait`으로만 접근한다.
- `thread`: `_run`을 실행하는 non-daemon `village-network` thread. 상위 계층은 `start`, `is_alive`, `join`으로만 접근한다.
- `_auth_factory`: `AuthFactoryPort`.
- `_api_factory`: `ApiClientFactoryPort`.
- `_game_socket_factory`: `GameSocketFactoryPort`.
- `_validator`: `ResponseValidatorPort`.
- `_authenticated`: worker 유스케이스의 현재 인증 여부.

## 공개 메서드

### `NetworkWorker.__init__(self, origin: str, auth_factory: AuthFactoryPort, api_factory: ApiClientFactoryPort, game_socket_factory: GameSocketFactoryPort, validator: ResponseValidatorPort) -> None`

```text
origin과 주입받은 추상 factory/validator 저장
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
trust_env=False인 단일 ClientSession 생성

AuthFactoryPort(session, origin) -> AuthPort
ApiClientFactoryPort(session, origin, validator, result sink) -> ApiClientPort
GameSocketFactoryPort(session, origin, validator, result sink) -> GameSocketPort

active, delivery_task, analytics_task, history_task 슬롯 유지
반복:
    완료 task await 후 슬롯 비우기
    request가 없으면 worker만 0.02초 yield
    stop이면 종료
    delivery/analytics/history는 각 전용 task 한 개만 허용
    일반 active는 한 개만 허용
    active 중 command가 오면 command_error 출력
    처리하지 않은 request credential 제거
finally:
    남은 task 취소 및 회수
    GameSocketPort.shutdown()
    AuthPort.clear()
    ClientSession context 종료
```

단일 thread·event loop·ClientSession 원칙은 분리 전과 같다.

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
history -> 인증 검사, ApiClientPort.get_history(), Result('history')
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
- delivery, analytics, history는 각각 독립 task 하나를 허용한다.
- 수련 성공 뒤 history 요청을 자동 제출한다.
- 모든 외부 응답은 검증된 `Result`로만 상위 계층에 전달한다.
- replay 요청이나 task는 없다.

