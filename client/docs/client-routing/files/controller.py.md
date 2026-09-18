# `client/controller.py`

## 책임과 경계

메인 스레드 애플리케이션 유스케이스를 조정한다. 로그인·조회·게임 명령을 `messages.Request`로 바꾸고, `messages.Result`를 상태·패널 포트에 배분한다. pygame 이벤트·Rect·프레임, HTTP/WS 형식, 구체 구현 클래스는 알지 않는다.

직접 호출하는 클라이언트 코드:

- `messages.Request`, `messages.Result`
- `ports.StatePort`
- `ports.AnalyticsPanelPort`, `ports.HistoryPanelPort`
- `ports.NetworkPort`

`state`, `panels`, `network` concrete 모듈은 import하지 않는다.

## `ClientController` 필드

- `state: StatePort`: 게임 상태 계약.
- `analytics_panel: AnalyticsPanelPort`, `history_panel: HistoryPanelPort`: 패널 상태 계약.
- `worker: NetworkPort`: 요청 제출과 종료 계약.

## 메서드

### `ClientController.__init__(self, state: StatePort, analytics_panel: AnalyticsPanelPort, history_panel: HistoryPanelPort, worker: NetworkPort) -> None`

```text
주입받은 상태와 worker 참조를 저장
새 상태나 네트워크 객체를 내부에서 만들지 않음
```

### `submit(self, kind: str) -> bool`

```text
busy/closing/command_pending이면 False
player/history/logout이고 delivery 또는 패널 요청 중이면 False
login이면 username/password 검사
    Request(kind, trimmed username, password) 생성
    두 패널 clear
    State.password 즉시 제거
그 외 Request(kind) 생성
State.busy=True와 요청 메시지 설정
NetworkPort.submit(request)
True 반환
```

### `request_command(self, action: str, direction: str = '') -> bool`

```text
State.begin_command(action, time.monotonic(), direction)
거부되면 False
train이면 HistoryPanelState.wait_for_train()
NetworkPort.submit(Request('command', direction=..., action=...))
True 반환
```

키보드와 마우스가 공유하는 유일한 게임 명령 유스케이스 경로다.

### `request_delivery(self) -> bool`

```text
State.begin_delivery(time.monotonic())
거부되면 False
NetworkPort.submit(Request('delivery'))
True 반환
```

### `request_analytics(self) -> bool`

```text
AnalyticsPanelPort.begin(authenticated, closing)이 거부하면 False
이력 패널 숨김
NetworkPort.submit(Request('analytics'))
True 반환
```

최초 조회와 미생성·오류 뒤 재조회는 이 메서드만 사용한다. `pending` 상태가 프레임 중복 요청과 연속 클릭을 막는다.

### `toggle_analytics(self) -> None`

```text
통계 패널이 보이면 hide()
아니면 request_analytics()
```

### `toggle_history(self) -> None`

```text
이력 패널이 보이면 hide()
아니고 통계 요청이 진행 중이 아니면:
    통계 패널 hide()
    이력 패널 show()
```

표시 토글만으로는 history API 요청을 만들지 않는다.

### `request_history(self) -> None`

```text
이력 요청이 진행 중이지 않고 submit('history')가 성공하면:
    HistoryPanelState.begin()
    통계 패널 hide()
```

### `begin_shutdown(self) -> bool`

```text
이미 closing이면 False
closing=True, password 제거, 종료 안내 메시지 설정
NetworkPort.stop()
True 반환
```

### `apply_result(self, result: Result) -> None`

```text
AnalyticsPanelState.apply(result)
HistoryPanelState.apply(result)
두 패널이 전용 처리하지 않았거나 needs_login이면 State.apply(result)
logged_out 또는 needs_login이면 두 패널 clear()
```

패널 결과 적용 순서와 로그인 만료 시 일반 상태 적용을 보존한다.
