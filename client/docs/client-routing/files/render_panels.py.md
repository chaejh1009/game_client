# `client/render_panels.py`

## 책임과 경계

API 응답, 확정 행동 통계, 최근 행동 이력 패널을 출력한다. 모든 값은 `StatePort`, `AnalyticsPanelPort`, `HistoryPanelPort`를 통해 전달받으며 서버 요청이나 패널 상태 전이를 수행하지 않는다.

## 함수

### `draw_api_panel(view, state, analytics_panel, history_panel) -> None`

고정 API 버튼, 최근 경로/status, 안전하게 투영된 JSON을 출력한다. 진행 중 상태를 읽어 버튼 비활성 표현만 결정한다.

### `draw_analytics_panel(view, panel) -> None`

visible이면 overlay를 출력한다. pending, 집계 없음, 미조회, 집계 결과를 구분하고 행동별·방별 최대 8행을 표시한다.

### `draw_history_panel(view, panel) -> None`

visible이면 overlay를 출력한다. pending/빈 이력 안내 또는 최근 최대 20개 이벤트의 시각·종류·transition을 표시한다.

각 함수는 clip 영역을 사용한 뒤 이전 clip을 복원한다.
