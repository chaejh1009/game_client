# `client/render.py`

## 창 크기 변경

`Renderer.resize(width, height)`, `scroll(amount)`, `pointer_to_content(pos)`, `text_input_rect(name)`은 `RenderSupport`의 viewport 기능에 위임한다. 장면 상태를 변경하거나 네트워크 요청을 수행하지 않는다.

## 책임과 경계

렌더 계층의 공개 façade이다. `RendererPort`를 구조적으로 구현하고 로그인/게임 장면을 선택해 같은 계층의 전용 모듈로 위임한다. `ClientApp`에는 `controls`, `draw(...)`, `resize(...)`, 스크롤과 좌표 변환 메서드를 노출한다.

구체 상태·패널·네트워크·controller 모듈은 import하지 않으며 다음 포트만 입력으로 사용한다.

- `ConfigPort`
- `StatePort`
- `AnalyticsPanelPort`
- `HistoryPanelPort`
- `AdsPanelPort`

## `Renderer`

### `Renderer.__init__(self, config: ConfigPort) -> None`

```text
RenderSupport(config)와 render_ads.AdsRenderer() 생성
RenderSupport.controls를 Renderer.controls로 공개
```

Pygame display/font 초기화는 기존대로 `ClientApp.run`이 먼저 수행한다.

### `Renderer.draw(self, state: StatePort, analytics_panel: AnalyticsPanelPort, history_panel: HistoryPanelPort, ads_panel: AdsPanelPort | None = None) -> None`

```text
배경 지우기
state.authenticated이면 render_game.draw_game 호출
아니면 render_login.draw_login 호출
미인증이면 scroll_y를 0으로 복원
ads_panel이 있고 인증·비종료·통계/이력 비표시·ads_visible()이면:
    AdsRenderer.draw(view, ads_panel)로 이미지 blit 여부 받기
RenderSupport.present(show_scroll=state.authenticated)로 viewport 표시 및 flip
이미지가 blit됐으면 AdsPanelPort.mark_displayed(time.monotonic())
```

기존 게임·통계·이력 상태는 읽기만 한다. 광고 준비 상태는 AdsRenderer.draw가, flip 후 표시 완료 상태는 AdsPanelPort.mark_displayed가 갱신한다.

### `Renderer.ads_visible(self) -> bool`

```text
view.display가 없거나 pygame.display.get_active()가 False이면 False
RenderSupport._viewport()로 보이는 콘텐츠 높이 계산
scroll_y <= ad_rect.top이고 ad_rect.bottom <= scroll_y + 높이이면 True, 그 외 False
```

### `Renderer.resize(self, width: int, height: int) -> None`

```text
RenderSupport.resize(width, height) 호출
```

`scroll`, `pointer_to_content`, `text_input_rect`도 같은 이름의 `RenderSupport` 메서드에 위임한다.

## 호출 관계

```text
ClientApp -> RendererPort
             -> render.Renderer
                -> render_support.RenderSupport
                -> render_login.draw_login
                -> render_game.draw_game
                -> render_ads.AdsRenderer.draw
                -> AdsPanelPort.mark_displayed (present/flip 후)
```

세부 책임은 다음 문서를 따른다.

- [`render_support.py.md`](render_support.py.md): 자산·글꼴·배치·공통 출력
- [`render_login.py.md`](render_login.py.md): 로그인 장면
- [`render_game.py.md`](render_game.py.md): 인증 후 화면 조정
- [`render_world.py.md`](render_world.py.md): 맵과 플레이어
- [`render_panels.py.md`](render_panels.py.md): API·통계·이력 패널과 하단 측정 카드
- [`render_ads.py.md`](render_ads.py.md): 광고 이미지 변환·출력과 준비 상태 콜백
