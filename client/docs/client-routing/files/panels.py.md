# `client/panels.py`

## 책임과 경계

선택형 정보 패널의 메인 스레드 상태 전이만 소유한다. `AnalyticsPanelState`와 `HistoryPanelState`는 각각 대응하는 panel port를 구조적으로 구현한다. 네트워크 요청을 만들지 않고, 렌더링하지 않으며, 검증이 끝난 `messages.Result`만 소비한다.

## `AnalyticsPanelState`

### 필드와 출처

- `visible`, `pending`: `controller.py`의 토글/요청과 `apply`가 관리한다.
- `available`, `schema_version`, `generated_at`, `event_count`, `by_action`, `by_room`: `Result(kind='analytics').player`에서 온 검증된 값.
- `message`: 진행·빈 집계·성공·오류 표시 문자열.

### `begin(self, authenticated: bool, closing: bool) -> bool`

```text
미인증, 종료 중, 기존 pending이면 False
visible=True, pending=True, 읽는 중 메시지 설정
True
```

### `hide(self) -> None`

```text
pending이 아닐 때만 visible=False
```

### `clear(self) -> None`

```text
표시/진행 상태와 모든 집계 값을 초기값으로 복원
```

### `apply(self, result: Result) -> bool`

```text
analytics이면:
    pending 해제
    available=False면 집계 필드 비우고 빈 집계 메시지
    available=True면 schema/generated/event_count/by_action/by_room 저장
    True
analytics_error이면 pending 해제, 오류 메시지 저장, True
그 외 False
```

반환값은 `controller.py`가 일반 `State.apply`에도 전달할지 결정하는 데 쓴다.

## `HistoryPanelState`

### 필드와 출처

- `visible`, `pending`: `controller.py` 토글과 수련/조회 결과가 관리한다.
- `scope`, `limit`, `events`: `Result(kind='history').player`에서 온 검증된 값.
- `message`: 초기 안내, 수련 대기, 읽는 중, 성공, 오류 문자열.

### `begin(self) -> bool`

```text
이미 pending이면 False
visible=True, pending=True, 읽는 중 메시지
True
```

### `wait_for_train(self) -> None`

```text
pending=True
수련 결과 대기 메시지 설정
```

### `show(self) -> None`

```text
visible=True
```

### `hide(self) -> None`

```text
visible=False
```

### `clear(self) -> None`

```text
표시/진행 상태와 history 데이터를 초기값으로 복원
```

### `apply(self, result: Result) -> bool`

```text
성공한 train command이면 pending 유지, history 자동 조회 안내, False
실패한 train command이면 pending 해제, 오류 메시지, False
history이면 scope/limit/events 저장, pending 해제, False
history_error이면 pending 해제, 오류 메시지, False
그 외 False
```

이력 결과도 일반 `State`의 API 검사 필드가 갱신될 수 있도록 현재는 항상 `False`를 반환한다.

## 패널 상호 배타성

두 패널은 서로를 직접 알지 않는다. `controller.py`가 통계 패널을 열 때 이력을 숨기고, 이력 패널을 열 때 통계를 숨긴다. replay 상태는 없다.
