# `client/render_panels.py`

## 책임과 경계

API 응답, 확정 행동 통계, Kafka 수집 통계, 최근 행동 이력 패널을 출력한다. 모든 값은 `StatePort`, `AnalyticsPanelPort`, `HistoryPanelPort`를 통해 전달받으며 서버 요청이나 패널 상태 전이를 수행하지 않는다.

## 함수

### `draw_api_panel(view, state, analytics_panel, history_panel) -> None`

고정 API 버튼, 최근 경로/status, 안전하게 투영된 JSON을 출력한다. 진행 중 상태를 읽어 버튼 비활성 표현만 결정한다.

### `draw_analytics_panel(view, panel) -> None`

visible이면 overlay를 출력하며 네트워크 요청이나 상태 변경은 하지 않는다.

- pending은 읽는 중으로 표시한다.
- `available=False`는 `행동 집계가 아직 없습니다`와 조회 버튼을 표시하며 0건으로 표현하지 않는다.
- 최초 오류는 오류 안내와 다시 조회 버튼을 표시한다.
- 성공 snapshot은 `source_topic`, `source_kind`, `generated_at`, `고유 행동 수`, `원본 전달 행 수`를 구분해 표시한다.
- `by_action`의 앞 세 항목은 왼쪽의 `action_label`·`count` 카드로, `by_room`의 앞 네 항목은 오른쪽의 방별 행동 수 목록으로 표시한다. 네 항목을 넘으면 추가 방 수를 안내하며 목록과 안내는 Kafka 카드 위에 배치한다. 긴 텍스트는 각 카드·방 이름 영역에서 잘라 그리며 없는 카드 값을 0으로 만들지 않는다.
- 접속자 수·잔액·현재 화면 이동 횟수와 다른 값이라는 설명과 `고정 snapshot · 마지막 집계 기준` 안내를 표시한다.
- 기존 snapshot 재조회 실패 시 기존 값과 오류 안내를 함께 표시한다.

같은 overlay 아래의 `Kafka 수집 통계` 카드는 `ingest_*` 상태만 읽는다.

- `통계 다시 읽기` 버튼은 이미 게시된 결과를 읽는다는 문구와 `Spark 실행 없음 · Kafka 연결 없음` 안내를 함께 표시한다.
- pending이 아니면 `GET /api/analytics/ingest/` 결과를 표시한다. 성공 시 `source`, `generated_at`, `수집 레코드`, `고유 사건`, `재전달 레코드`와 `event_type`·`count` 목록을 그린다.
- available=false는 reason을 준비 안내로 보여 주고 숫자 0을 만들지 않는다. 503은 전달받은 `마지막 수집 통계를 읽을 수 없음` 오류 안내를 카드에 표시한다.
- 원문 `raw_value`나 evidence 파일을 읽지 않으며, 렌더 함수는 텍스트·Rect·Surface 출력만 수행한다.

302/401의 로그인 필요 결과는 [controller.py](controller.py.md)가 처리하며 패널을 초기화한다. 로그인 안내는 [render.py](render.py.md)가 선택한 [render_login.py](render_login.py.md)의 로그인 화면에서 표시한다.

### `draw_history_panel(view, panel) -> None`

visible이면 overlay를 출력한다. pending/빈 이력 안내 또는 최근 최대 20개 이벤트의 시각·종류·transition을 표시한다.

각 함수는 clip 영역을 사용한 뒤 이전 clip을 복원한다.
