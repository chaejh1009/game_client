# `client/render_support.py`

## 책임과 경계

렌더 계층의 공통 Pygame 인프라를 소유한다. 창, 글꼴, 이미지, 고정 배치와 hitbox를 준비하고 텍스트·버튼·타일·스프라이트 출력 primitive를 제공한다. 애플리케이션 상태나 패널 상태는 알지 않는다.

## 값

- 화면 색상과 fallback 색상
- `TILE_SIZE = 32`, `MAP_COLUMNS = 20`, `MAP_ROWS = 15`
- `CONFIRMED_IMAGE_SIZE = (16, 16)`

## `RenderSupport`

### `__init__(config: ConfigPort)`

```text
설정 크기로 Pygame 창 생성 및 제목 지정
_prepare_fonts와 _prepare_assets 호출
_prepare_layout으로 map/slot/control/API panel Rect 계산
```

### `_prepare_fonts()`, `_prepare_assets()`

설정의 글꼴·이미지 경로를 준비한다. 실패하면 기본 글꼴 또는 fallback 도형을 사용하고 `asset_errors`에 안전한 안내만 저장한다.

### `_prepare_layout()`

기존 좌표로 `map_rect`, `slots`, `api_panel`, `controls`를 만든다. `controls`의 Pygame Rect는 `HitTargetPort.collidepoint` 계약을 구조적으로 만족한다.

### 출력 primitive

- `text`, `wrapped`: 문자열 출력
- `button`: control hitbox와 같은 위치에 버튼 출력
- `draw_slot`: sidebar slot 배경 출력
- `draw_tile`, `draw_sprite_at_tile`: 자산 또는 fallback 도형 출력

논리 타일 위치는 서버 상태를 변경하지 않으며 화면 좌표로만 변환한다.
