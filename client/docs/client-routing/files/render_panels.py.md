# `client/render_panels.py`

## 책임과 경계

API 응답, 확정 행동 통계, Kafka 수집 통계, 확정 시간 창 표, 최근 행동 이력 패널을 출력한다. 모든 값은 `StatePort`, `AnalyticsPanelPort`, `HistoryPanelPort`를 통해 전달받으며 서버 요청이나 패널 상태 전이를 수행하지 않는다. Pygame 글꼴·Rect·Surface 출력은 메인 스레드에서 수행한다.

## 함수

### `draw_api_panel(view, state, analytics_panel, history_panel) -> None`

```text
API 영역 clip 설정
인증/종료/요청 진행 상태로 player/history/windows/analytics 버튼 비활성 여부 결정
네 버튼과 현재 선택한 경로 강조 출력
StatePort.api_path, api_status, api_json을 경로·status·JSON으로 출력
이전 clip 복원
```

`windows` 버튼의 경로는 `/api/analytics/windows/`, `analytics` 버튼의 경로는 `/api/analytics/`이다. `windows_pending`도 다른 요청과 함께 버튼 비활성 조건에 포함한다. JSON은 검증 계층이 안전하게 투영한 응답만 사용하며 auth·쿠키·CSRF 필드를 만들거나 출력하지 않는다.

### `draw_analytics_panel(view, panel) -> None`

```text
panel이 없거나 visible=False이면 반환
overlay Rect와 clip 준비
기존 통계(summary)/시간 창(windows) 탭 출력 및 선택 강조
시간 창 탭이면 _draw_windows_panel 호출, 이전 clip 복원 후 반환
summary 탭이면 확정 사실 집계 카드와 Kafka 수집 통계 출력
이전 clip 복원
```

탭을 그릴 때 네트워크 요청이나 상태 변경은 하지 않는다. 기존 통계 탭의 출력 계약은 다음과 같다.

- pending은 읽는 중으로 표시한다.
- 행동 통계·ingest·windows 중 요청이 진행 중이면 기존 통계의 조회와 `통계 다시 읽기` 버튼도 비활성으로 표시한다.
- `available=False`는 `아직 집계 없음`으로 표시하며 0건으로 표현하지 않는다.
- 최초 오류는 오류 안내와 `새로 읽기` 버튼을 표시한다.
- 성공 snapshot은 `source=raw/delta`를 각각 `DB 내보내기 스냅샷`/`event_id별 고유 사실 Delta`로, `generated_at`을 `집계 생성 시각`으로 표시한다. `event_count`는 `고유 확정 사실 수`, 선택적 `record_count`는 `선택한 원천의 행 수`로 구분한다.
- `by_action`의 앞 네 `event_type`/`count`, `by_room`의 앞 네 `room_id`/`count`를 두 표로 표시한다. 빈 배열은 `게시할 그룹 없음`으로 표시하고, 더 많은 행은 남은 그룹 수를 안내한다. 긴 레이블은 셀 안에서 자르며 값은 일반 텍스트로 그려 평가하지 않는다.
- `새로 읽기` 버튼은 한 번 누를 때 한 GET만 요청한다.
- 접속자 수·잔액·현재 화면 이동 횟수와 다른 값이라는 설명과 `고정 snapshot · 마지막 집계 기준` 안내를 표시한다.
- 기존 snapshot 재조회 실패 시 기존 값과 오류 안내를 함께 표시한다.

같은 overlay 아래의 `Kafka 수집 통계` 카드는 `ingest_*` 상태만 읽는다.

- `통계 다시 읽기` 버튼은 이미 게시된 결과를 읽는다는 문구와 `Spark 실행 없음 · Kafka 연결 없음` 안내를 함께 표시한다. 그 아래에 `확정 사실은 먼저 수집됩니다. 뒤 시각의 레코드로 watermark가 진행된 뒤 창이 확정됩니다. 창 요 약을 갱신한 다음 통계를 조회하세요.` 도움말을 줄 바꿈해 표시하며, 아래 상태·통계 값의 출력 위치를 조정해 겹치지 않게 한다.
- pending이 아니면 `GET /api/analytics/ingest/` 결과를 표시한다. 성공 시 `source`, `generated_at`, `수집 레코드`, `고유 사건`, `재전달 레코드`와 `event_type`·`count` 목록을 그린다.
- available=false는 reason을 준비 안내로 보여 주고 숫자 0을 만들지 않는다. 503은 전달받은 `마지막 수집 통계를 읽을 수 없음` 오류 안내를 카드에 표시한다.
- 원문 `raw_value`나 evidence 파일을 읽지 않으며, 렌더 함수는 텍스트·Rect·Surface 출력만 수행한다.

302/401의 로그인 필요 결과는 [controller.py](controller.py.md)가 처리하며 패널을 초기화한다. 로그인 안내는 [render.py](render.py.md)가 선택한 [render_login.py](render_login.py.md)의 로그인 화면에서 표시한다.

### `_draw_windows_panel(view, panel, rect) -> None`

```text
'확정 시간 창의 전달 레코드 수(중복 전달 포함 가능)' 표제 출력
'시작 포함 · 끝 미포함 [window_start, window_end)' 구간 설명 출력
windows_generated_at을 '집계 생성 시각'으로 출력, 값이 없으면 —
all/tumbling/sliding 필터 선택과 새로 읽기 버튼 출력
행동 통계·ingest·windows 중 요청 진행 시 새로 읽기 비활성 표현
진행 중/오류/일반 windows 안내를 구분해 출력
available이 True가 아니거나 전체 창 배열이 비면 반환
현재 필터의 페이지 행이 비면 선택한 종류의 창 없음 안내 후 반환
kind/window_start/window_end/event_type/count 5열과 최대 5행 출력
이전/다음 버튼, 현재 페이지/페이지 수, 필터 결과 행 수 출력
```

- `available=false` 안내는 `아직 창 요약 없음`, `available=true`의 빈 배열 안내는 `확정된 게시 대상 창 없음`으로 구분한다.
- 각 셀에서 시간 문자열과 event_type을 줄바꿈하고 clip을 복원해 인접한 count 열과 겹치지 않게 한다.
- 필터와 페이지는 `AnalyticsPanelPort.visible_windows`, `window_page_rows`, `window_page_count`를 읽는다. 서버 조회나 Spark 실행을 하지 않는다.
- 오류가 나도 패널에 보관된 기존 행과 집계 생성 시각을 함께 출력할 수 있다. 시간 창 결과로 게임 player 요약이나 온라인 상태를 대체하지 않는다.

### `draw_history_panel(view, panel) -> None`

visible이면 overlay를 출력한다. pending/빈 이력 안내 또는 최근 최대 20개 이벤트의 시각·종류·transition을 표시한다.

각 함수는 clip 영역을 사용한 뒤 이전 clip을 복원한다.
