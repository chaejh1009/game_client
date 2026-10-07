# `client/controller.py`

## 측정 조회

`request_measurement(kind)`는 `AnalyticsPanelPort.begin_measurement`가 허용할 때만 `Request(kind)`를 `NetworkPort.submit`에 전달한다. worker 결과는 기존 `apply_result`에서 패널의 `apply`를 거치며 로그인 만료 시 기존 계정·패널 초기화 경로를 따른다.

## 책임과 경계

메인 스레드 애플리케이션 유스케이스를 조정한다. 로그인·조회·게임 명령을 `messages.Request`로 바꾸고, `messages.Result`를 상태·패널 포트에 배분한다. pygame 이벤트·Rect·프레임, HTTP/WS 형식, 구체 구현 클래스는 알지 않는다.

직접 호출하는 클라이언트 코드:

- `messages.Request`, `messages.Result`
- `ports.StatePort`
- `ports.AnalyticsPanelPort`, `ports.HistoryPanelPort`, `ports.AdsPanelPort`
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
player/history/logout이고 delivery 또는 통계·ingest·windows·이력 패널 요청 중이면 False
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

통계 패널을 열 때와 `새로 읽기` 또는 API 응답 보기의 `집계` 버튼을 누를 때 이 메서드를 사용한다. 성공한 snapshot도 다시 읽을 수 있다. `pending` 상태가 프레임 중복 요청과 연속 클릭을 막는다.

### `request_ingest(self) -> bool`

```text
AnalyticsPanelPort.begin_ingest(authenticated, closing)이 거부하면 False
이력 패널 숨김
NetworkPort.submit(Request('ingest'))
True 반환
```

`통계 다시 읽기` 버튼의 유일한 진입점이다. 이미 게시된 결과를 읽는 GET만 worker에 제출하고, `ingest_pending`으로 프레임 반복과 연속 클릭을 막는다.

### `request_windows(self) -> bool`

```text
AnalyticsPanelPort.begin_windows(authenticated, closing)이 거부하면 False
이력 패널 숨김
NetworkPort.submit(Request('windows'))
True 반환
```

시간 창 `새로 읽기` 버튼의 요청 진입점이다. 한 번의 클릭으로 한 요청만 queue에 제출하고, `windows_pending`으로 진행 중 중복 요청을 막는다.

### `request_measurement(self, kind: str) -> bool`

```text
AnalyticsPanelPort.begin_measurement(kind, authenticated, closing)이 거부하면 False
NetworkPort.submit(Request(kind))
True 반환
```

### 시간 창의 로컬 표시 선택

```text
select_analytics_view(view) -> AnalyticsPanelPort.select_analytics_view(view)
select_window_kind(kind) -> AnalyticsPanelPort.select_window_kind(kind)
change_window_page(delta) -> AnalyticsPanelPort.change_window_page(delta)
```

세 메서드는 패널의 탭·필터·페이지만 변경하며 worker를 호출하지 않는다.

### `toggle_analytics(self) -> None`

```text
통계 패널이 보이면 hide()
아니면 request_analytics()
```

### `toggle_history(self) -> None`

```text
이력 패널이 보이면 hide()
아니고 통계·ingest·windows 요청이 진행 중이 아니면:
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
`analytics`/`analytics_error`, `windows`/`windows_error`, `load`/`load_error`, `metrics`/`metrics_error`는 통계 패널이 소비하여 게임 플레이어 상태와 섞이지 않는다. API 조회의 `Result(kind='api')`는 별도로 일반 상태에 전달되어 경로·status·검증된 JSON만 API 응답 보기에 표시한다. `needs_login` 결과만 기존 로그인 안내와 패널 초기화 흐름을 따른다.

### `request_ad_event(self, panel: AdsPanelPort, event_type: str) -> bool`

```text
monotonic 시각과 decision_id 확인
미인증·종료·게시판 아님·결정 없음/empty·미표시·영구 거절·준비 아님·재시도 시각 이전이면 False
impression은 pending/ok이면 False; 아니면 impression_pending=True
click은 impression_ok가 아니거나 click_pending/click_ok이면 False; 아니면 click_requested/click_pending=True
그 외 event_type이면 False
event_error 제거, 저장 중 메시지 설정
NetworkPort.submit(Request('ad_event', request_id=panel.request_id, slot_id=panel.slot_id,
                           decision_id=decision_id, event_type=event_type))
True 반환
```

노출 확인 전 클릭은 요청을 제출하거나 `click_requested`를 설정하지 않는다. 허용된 클릭이 일시 실패하면 프레임 루프가 `click_requested`를 보고 재시도를 요청하며, 재시도 시각 검사는 이 메서드가 담당한다.
