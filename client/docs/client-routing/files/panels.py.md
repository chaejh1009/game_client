# `client/panels.py`

## 책임과 경계

선택형 정보 패널의 메인 스레드 상태 전이만 소유한다. `AnalyticsPanelState`와 `HistoryPanelState`는 각각 대응하는 panel port를 구조적으로 구현한다. 네트워크 요청을 만들지 않고, 렌더링하지 않으며, 검증이 끝난 `messages.Result`만 소비한다.

## `AnalyticsPanelState`

### 필드와 출처

- `visible`, `pending`: `controller.py`의 토글/요청과 `apply`가 관리한다.
- `available`, `source_topic`, `source_kind`, `raw_record_count`: `Result(kind='analytics').player`에서 온 검증된 최상위 값.
- `generated_at`, `event_count`, `by_action`, `by_room`: 검증된 `summary`에서 온 snapshot 값.
- `message`, `error`: 진행·미생성·성공·오류를 구분하는 표시 문자열.
- `ingest_pending`, `ingest_available`, `ingest_source`, `ingest_generated_at`: `Result(kind='ingest').player`의 Kafka 수집 snapshot 상태.
- `ingest_record_count`, `ingest_event_count`, `ingest_duplicate_record_count`, `ingest_by_action`: 검증된 수집 레코드·고유 사건·재전달 레코드·`event_type`별 목록.
- `ingest_message`, `ingest_error`: 수집 snapshot 준비·성공·오류 안내.

### `begin(self, authenticated: bool, closing: bool) -> bool`

```text
미인증, 종료 중, 행동 집계 또는 ingest 기존 pending이면 False
visible=True, pending=True, 읽는 중 메시지 설정
이전 오류 문자열 제거
True
```

### `hide(self) -> None`

```text
행동 집계와 ingest 어느 쪽도 pending이 아닐 때만 visible=False
```

### `begin_ingest(self, authenticated: bool, closing: bool) -> bool`

```text
미인증, 종료 중, 행동 집계 또는 기존 ingest pending이면 False
visible=True, ingest_pending=True, 수집 통계 읽는 중 메시지 설정
이전 ingest 오류 문자열 제거
True
```

### `clear(self) -> None`

```text
표시/진행 상태와 모든 집계 값을 초기값으로 복원
```

### `apply(self, result: Result) -> bool`

```text
analytics이면:
    pending 해제
    오류 문자열 제거
    available=False면 숫자를 0으로 만들지 않고 집계 필드를 비운 뒤 '행동 집계가 아직 없습니다' 설정
    available=True면 source 정보, raw_record_count와 summary snapshot 저장
    True
analytics_error이면 pending 해제, 오류 메시지 저장, 기존 성공 snapshot은 보존, True
ingest이면 ingest_pending 해제
    available=False면 수치 필드를 비우고 reason을 친절한 준비 안내로 변환
    available=True면 source/generated_at/세 카운트와 event_type별 목록 저장
    True
ingest_error이면 ingest_pending 해제, 오류 메시지 저장, 기존 수집 snapshot은 보존, True
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

두 패널은 서로를 직접 알지 않는다. `controller.py`가 통계 또는 ingest 패널을 열 때 이력을 숨기고, 이력 패널을 열 때 통계를 숨긴다. replay 상태는 없다.
