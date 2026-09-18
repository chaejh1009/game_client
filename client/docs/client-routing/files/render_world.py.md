# `client/render_world.py`

## 책임과 경계

서버가 확정한 월드 상태를 화면에 투영한다. 지형, 채굴·수련 지점, 장식, 플레이어를 그리며 게임 규칙이나 충돌 상태를 만들지 않는다.

## `draw_world(view: RenderSupport, state: StatePort) -> None`

```text
map_rect로 clip
20×15 grass/path 타일 출력
(2,2) 채굴 지점과 (3,2) 수련 지점 표시
충돌과 무관한 나무·집 장식 출력
state.players를 자기 player가 마지막이 되도록 정렬
player sprite, outline, player_id 출력
clip 복원
```

낮은 version 거부와 player 병합은 `state.py` 책임이며 이 모듈은 전달받은 값을 읽기만 한다.
