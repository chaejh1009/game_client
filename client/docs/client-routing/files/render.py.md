# `client/render.py`

## 책임과 경계

메인 스레드 전용 pygame 표현 계층이다. `RendererPort`를 구조적으로 구현하고, 검증된 상태·패널 포트를 읽어 화면을 그리며 입력 hitbox를 제공한다. 네트워크 요청을 만들거나 상태 객체를 변경하지 않는다.

## 상수

- 색상: `BG`, `CARD`, `INK`, `MUTED`, `ACCENT`, `PENDING`, `ERROR`, `TRAIN`.
- fallback 색상: `GRASS_FALLBACK`, `PATH_FALLBACK`.
- `TILE_SIZE = 32`: 현재 실제 렌더링 타일 크기.
- `MAP_COLUMNS = 20`, `MAP_ROWS = 15`: 화면 맵 크기.
- `CONFIRMED_IMAGE_SIZE = (16, 16)`: 원본 자산 허용 크기.

## `Renderer` 필드와 출처

- `config`: `state.Config`.
- `screen`: `pygame.display.set_mode` 결과.
- `asset_errors`: 글꼴/이미지 준비 실패 메시지.
- `font`, `small`, `tiny`, `title`: `_prepare_fonts`가 만든 pygame Font.
- `assets`: `_prepare_assets`가 만든 이름→Surface 또는 `None` 매핑.
- `map_rect`, `slots`, `api_panel`: 창 크기와 고정 배치에서 계산한 Rect.
- `controls`: `RendererPort`가 공개하고 `client_app.py`가 `HitTargetPort`로 사용하는 컨트롤 이름→클릭 Rect 매핑.

## 초기화와 공통 primitive

### `Renderer.__init__(self, config: ConfigPort) -> None`

```text
config 저장
pygame 창 생성 및 제목 설정
asset_errors 초기화
_prepare_fonts(), _prepare_assets()
창 너비를 기준으로 map/sidebar/slot/control/API panel Rect 계산
```

외부 호출: `pygame.display`, `pygame.Rect`.

### `_prepare_fonts(self) -> None`

```text
config.font_path가 없거나 파일이 아니면 시스템 한글 글꼴 탐색
19/14/12/30 크기 Font 생성
실패하면 asset_errors 기록 후 pygame 기본 글꼴 사용
```

### `_prepare_assets(self) -> None`

```text
config의 grass/path/tree/house/hero 경로 매핑
각 파일을 alpha 이미지로 로드
원본 크기가 16x16이 아니면 실패 처리
32x32로 scale해 assets에 저장
실패하면 None과 asset_errors 기록
```

### `text(self, value, pos, color=INK, font=None) -> None`

```text
값을 문자열로 렌더링
screen.blit(surface, pos)
```

### `wrapped(self, value, x: int, y: int, width: int, font=None, color=MUTED) -> int`

```text
문자 단위로 너비를 측정해 줄 분할
각 줄을 text로 출력
다음 y 좌표 반환
```

### `button(self, name: str, label: str, disabled: bool = False, color=None) -> None`

```text
controls[name] Rect 조회
disabled/지정/강조 색으로 둥근 사각형 그리기
가운데 label 출력
```

## 게임 화면 helper

### `_command_color(self, state: State, action: str, direction: str = '') -> tuple[bool, tuple]`

```text
현재 선택 action인지, move이면 direction도 같은지 판별
pending/success/error 상태 색 또는 기본색 반환
```

### `_draw_commands(self, state, analytics_panel=None, history_panel=None) -> None`

```text
이동/채굴 버튼의 선택색과 비활성 조건 계산 후 button 호출
수련은 인증+WS 연결+(3,2)+idle일 때만 활성화
refresh/logout은 공통 요청, 명령, delivery, analytics 진행 상태로 비활성화
```

### `_draw_delivery(self, state: State) -> None`

```text
monotonic 시각으로 5초 cooldown 표시 계산
delivery 버튼 출력
event_count/pending_publish_count/source를 village-board slot에 출력
```

### `_draw_slot(self, name: str) -> None`

```text
slots[name]에 CARD 배경 출력
```

### `_draw_tile(self, name: str, x: int, y: int, fallback) -> pygame.Rect`

```text
논리 타일을 화면 Rect로 변환
asset이 없으면 fallback 색, 있으면 이미지 출력
Rect 반환
```

### `_draw_sprite_at_tile(self, name: str, x: int, y: int, fallback) -> None`

```text
논리 타일 Rect 계산
asset이 없으면 축소 fallback 도형
있으면 sprite 발 위치가 타일 하단 중앙에 오도록 출력
```

### `_draw_map(self, state: State) -> None`

```text
map_rect로 clip
20x15 grass/path 바닥 출력
(2,2) 채굴 지점과 (3,2) 수련 지점 표시
충돌 규칙에 영향 없는 나무/집 장식 출력
state.players를 자기 player가 마지막에 그려지도록 정렬
각 player sprite, outline, player_id 출력
clip 복원
```

### `_draw_command_status(self, state: State) -> None`

```text
선택 action/direction을 한국어 label로 변환
pending/success/error 문구와 색 추가
조작 안내/상태 메시지 출력
```

### `_draw_analytics_panel(self, panel: AnalyticsPanelState | None) -> None`

```text
없거나 숨김이면 반환
overlay와 clip 설정
pending/available=False/미조회 상태를 각각 출력
available=True이면 전체 건수, 생성시각, schema 출력
by_action과 by_room을 최대 8행씩 2열 표로 출력
clip 복원
```

### `_draw_api_panel(self, state, analytics_panel=None, history_panel=None) -> None`

```text
API panel 배경과 /api/player/, /api/history/ 버튼 출력
진행 상태에 따른 비활성 조건 계산
최근 api_path/status와 안전한 api_json을 JSON 문자열로 출력
```

### `_draw_history_panel(self, panel: HistoryPanelState | None) -> None`

```text
없거나 숨김이면 반환
overlay와 clip 설정
pending 또는 빈 events면 message 출력
그 외 scope/limit와 최근 최대 20개 event 출력
transition이 없으면 '확장 이전 기록'
있으면 step/reward와 reward 부호 색 출력
clip 복원
```

### `_draw_game(self, state, analytics_panel=None, history_panel=None) -> None`

```text
제목, 자기 player 통계, 특수 타일 안내 출력
_draw_map
village-board/lobby-banner slot 출력
방/온라인/WS 마지막 메시지 출력
_draw_delivery, _draw_commands
통계/이력 토글 버튼 출력
_draw_command_status, _draw_api_panel
_draw_analytics_panel, _draw_history_panel을 overlay 순서로 호출
```

### `_draw_login(self, state: State) -> None`

```text
제목과 server_base_url 출력
username/password 입력 상자와 focus 표시
password는 길이만큼 '*'로 마스킹
login 버튼, 키 안내, 상태 메시지 출력
asset_errors가 있으면 오류색으로 출력
```

### `draw(self, state, analytics_panel=None, history_panel=None) -> None`

```text
배경 지우기
authenticated이면 _draw_game, 아니면 _draw_login
pygame.display.flip()
```

## 자산 및 호출 관계

```text
ClientApp.run -> RendererFactoryPort(config) -> RendererPort
              -> 매 frame RendererPort.draw(state, analytics_panel, history_panel)

Renderer -> Config의 이미지/글꼴 경로
         -> client/assets/grass.png, path.png, tree.png, house.png, hero.png
         -> pygame draw/font/image/display API
```

행동 통계는 검증된 패널 상태만 그리며 `/api/analytics/`를 직접 호출하지 않는다. replay UI는 없다.
