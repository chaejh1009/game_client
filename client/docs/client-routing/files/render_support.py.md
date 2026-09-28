# `client/render_support.py`

## 책임과 경계

Pygame 창, 글꼴, 이미지, 가상 콘텐츠 화면과 공통 출력 primitive를 소유한다. 애플리케이션 상태나 네트워크 요청은 알지 않는다. `Renderer`가 이 객체를 통해 창 크기·스크롤·입력 좌표를 일관되게 처리한다.

## 값

- 화면 색상과 fallback 색상
- `TILE_SIZE = 32`, `MAP_COLUMNS = 20`, `MAP_ROWS = 15`
- `CONFIRMED_IMAGE_SIZE = (16, 16)`

## `RenderSupport`

### `__init__(config: ConfigPort)`

설정한 창 너비·높이 그대로 `RESIZABLE` display를 만들고, 960px 너비와 게임 영역 아래 측정 카드까지 포함하는 가상 `screen` Surface를 만든다. 글꼴·이미지와 모든 콘텐츠 좌표의 Rect를 준비한다.

### `resize`, `scroll`, `_viewport`, `_clamp_scroll`

`resize(width, height)`는 최소 640×600을 적용해 display만 바꾸고 스크롤 범위를 다시 제한한다. `_viewport`는 display 폭에 맞는 최대 1배 배율, 가로 중앙 여백과 현재 보이는 콘텐츠 높이를 계산한다. `scroll(amount)`는 콘텐츠 높이를 넘지 않도록 `scroll_y`를 조정한다. 로그인으로 돌아가면 `Renderer`가 스크롤을 맨 위로 복원한다.

### `pointer_to_content`, `text_input_rect`, `present`

`pointer_to_content`는 마우스 좌표를 가로 중앙 여백·배율·스크롤을 반영한 콘텐츠 좌표로 변환한다. `text_input_rect`는 IME 입력 위치를 반대 방향으로 변환한다. `present(show_scroll)`는 보이는 가상 화면 부분만 display에 그려 중앙 정렬하고, 게임 화면에서 필요한 경우 오른쪽 스크롤 표시를 그린 뒤 한 번 flip한다.

### `_prepare_fonts`, `_prepare_assets`

설정의 글꼴·이미지 경로를 준비한다. 실패하면 기본 글꼴 또는 fallback 도형을 사용하고 `asset_errors`에 안내만 저장한다.

### `_prepare_layout`, `_prepare_measurement_layout`

게임 맵, sidebar, API 패널, 모든 버튼 hitbox를 가상 화면의 콘텐츠 좌표로 만든다. 로그인 입력 폼은 480px 폭으로 중앙에 둔다. 부하·전달 측정 카드는 게임 영역 아래 y=732에서 나란히 둔다. 크기 변경은 콘텐츠 좌표를 바꾸지 않으며 display viewport만 갱신한다.

### 출력 primitive

- `text`: 글꼴·값·색 조합별 렌더 Surface를 최대 512개 캐시한다.
- `wrapped`: 글꼴·값·폭 조합별 줄 나눔을 최대 256개 캐시한다.
- `button`: control hitbox와 같은 콘텐츠 좌표에 버튼을 그린다.
- `draw_slot`: sidebar slot 배경을 그린다.
- `draw_tile`, `draw_sprite_at_tile`: 자산 또는 fallback 도형을 그린다.

Rect 생성과 자산·글꼴 준비는 pygame 초기화 뒤 메인 스레드에서 이뤄진다. 논리 타일 위치는 서버 상태를 변경하지 않으며 화면 좌표로만 변환한다.
