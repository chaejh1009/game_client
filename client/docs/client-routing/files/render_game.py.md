# `client/render_game.py`

## 책임과 경계

인증 후 게임 장면을 조정한다. player 요약, 방/WS 정보, delivery·명령 HUD, 토글 버튼을 출력하고 월드와 패널 출력은 전용 모듈에 위임한다. 상태 변경이나 controller 호출은 하지 않는다.

## 내부 helper

- `_command_color`: 선택 명령과 상태에 따른 색상 계산
- `_draw_commands`: 이동·채굴·수련·갱신·로그아웃 버튼 상태 출력. 행동 통계 또는 Kafka 수집 통계 요청 중에는 갱신·로그아웃을 비활성화한다.
- `_draw_delivery`: 5초 cooldown과 전달 카운트 출력
- `_draw_command_status`: 선택 명령과 결과 메시지 출력

## `draw_game(view, state, analytics_panel, history_panel) -> None`

```text
player 요약과 특수 타일 안내 출력
render_world.draw_world 호출
방/온라인/delivery/WS 정보 출력
명령과 패널 토글 버튼 출력
명령 상태 출력
render_panels의 API, analytics, history 함수를 overlay 순서로 호출
```

수련 버튼은 인증, WS 연결, `(3, 2)`, 명령 idle 조건을 모두 만족할 때만 활성화해서 그린다. 실제 명령 허용 여부는 `StatePort.begin_command`가 최종 결정한다.
