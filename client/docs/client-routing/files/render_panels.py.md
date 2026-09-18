# `client/render_panels.py`

## 책임과 경계

API 응답, 확정 행동 통계, 최근 행동 이력 패널을 출력한다. 모든 값은 `StatePort`, `AnalyticsPanelPort`, `HistoryPanelPort`를 통해 전달받으며 서버 요청이나 패널 상태 전이를 수행하지 않는다.

## 함수

### `draw_api_panel(view, state, analytics_panel, history_panel) -> None`

고정 API 버튼, 최근 경로/status, 안전하게 투영된 JSON을 출력한다. 진행 중 상태를 읽어 버튼 비활성 표현만 결정한다.

### `draw_analytics_panel(view, panel) -> None`

visible이면 overlay를 출력하며 네트워크 요청이나 상태 변경은 하지 않는다.

- pending은 읽는 중으로 표시한다.
- `available=False`는 `행동 집계가 아직 없습니다`와 조회 버튼을 표시하며 0건으로 표현하지 않는다.
- 최초 오류는 오류 안내와 다시 조회 버튼을 표시한다.
- 성공 snapshot은 `source_topic`, `source_kind`, `generated_at`, `고유 행동 수`, `원본 전달 행 수`를 구분해 표시한다.
- `by_action`의 앞 세 항목은 `action_label`과 `count` 카드로, `by_room`은 방별 행동 수 목록으로 표시한다. 없는 카드 값을 0으로 만들지 않는다.
- 접속자 수·잔액·현재 화면 이동 횟수와 다른 값이라는 설명과 `고정 snapshot · 마지막 집계 기준` 안내를 표시한다.
- 기존 snapshot 재조회 실패 시 기존 값과 오류 안내를 함께 표시한다.

### `draw_history_panel(view, panel) -> None`

visible이면 overlay를 출력한다. pending/빈 이력 안내 또는 최근 최대 20개 이벤트의 시각·종류·transition을 표시한다.

각 함수는 clip 영역을 사용한 뒤 이전 clip을 복원한다.
