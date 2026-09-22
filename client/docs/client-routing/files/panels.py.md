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
- `windows_pending`, `windows_available`, `windows_generated_at`, `windows`: `Result(kind='windows').player`의 검증된 시간 창 snapshot과 집계 생성 시각.
- `windows_message`, `windows_error`: 조회 전·진행·미생성·빈 목록·성공·오류 안내.
- `analytics_view`: `summary` 또는 `windows` 탭. 기본값 `summary`.
- `window_kind`, `window_page`: 메인 스레드에서 선택한 `all`/`tumbling`/`sliding` 필터와 0부터 시작하는 페이지. 기본값 `all`, `0`.
- `WINDOW_PAGE_SIZE=5`: 한 페이지에 표시할 창 행 수.

### `begin(self, authenticated: bool, closing: bool) -> bool`

```text
미인증, 종료 중, 행동 집계·ingest·windows 중 기존 pending이면 False
visible=True, pending=True, 읽는 중 메시지 설정
이전 오류 문자열 제거
True
```

### `hide(self) -> None`

```text
행동 집계·ingest·windows 모두 pending이 아닐 때만 visible=False
```

### `begin_ingest(self, authenticated: bool, closing: bool) -> bool`

```text
미인증, 종료 중, 행동 집계·ingest·windows 중 기존 pending이면 False
visible=True, ingest_pending=True, 수집 통계 읽는 중 메시지 설정
이전 ingest 오류 문자열 제거
True
```

### `begin_windows(self, authenticated: bool, closing: bool) -> bool`

```text
미인증, 종료 중, 행동 집계·ingest·windows 중 기존 pending이면 False
visible=True, analytics_view='windows', windows_pending=True
시간 창 읽는 중 메시지 설정, 이전 windows 오류 문자열 제거
True
```

### `select_analytics_view(self, view: str) -> None`

```text
view가 summary/windows이면 analytics_view만 변경
```

### `select_window_kind(self, kind: str) -> None`

```text
kind가 all/tumbling/sliding이면 window_kind 변경, window_page=0
```

### 로컬 필터와 페이지

```text
visible_windows -> all이면 보관한 windows, 아니면 kind가 일치하는 행 tuple
window_page_count -> 필터된 행 수를 5개씩 나눈 페이지 수, 최소 1
window_page_rows -> 필터된 행에서 현재 페이지의 최대 5개 행 tuple
change_window_page(delta) -> 0부터 마지막 페이지 사이로 페이지 이동 제한
```

탭·필터·페이지 선택은 이미 받은 배열만 사용하며 HTTP 요청이나 서버 설정 변경을 만들지 않는다.

### `clear(self) -> None`

```text
표시/진행 상태와 모든 집계 값을 초기값으로 복원
시간 창 snapshot/안내와 탭·필터·페이지 선택도 초기값으로 복원
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
windows이면 windows_pending 해제
    available/generated_at/windows snapshot 저장, 오류 제거, window_page=0
    available=False면 '아직 창 요약 없음'
    available=True이고 windows가 비면 '확정된 게시 대상 창 없음'
    행이 있으면 마지막 집계 snapshot 안내
    True
windows_error이면 windows_pending 해제, 오류 메시지 저장, 기존 창 snapshot/생성 시각 보존, True
그 외 False
```

반환값은 `controller.py`가 일반 `State.apply`에도 전달할지 결정하는 데 쓴다.
시간 창 성공 결과는 이 패널이 소비하므로 현재 게임 플레이어의 `coords`·`coins`·`version`을 대체하지 않는다.

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

두 패널은 서로를 직접 알지 않는다. `controller.py`가 통계·ingest·windows 요청을 시작할 때 이력을 숨기고, 이력 패널을 열 때 통계를 숨긴다. replay 상태는 없다.
