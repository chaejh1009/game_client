# `client/render.py`

## 책임과 경계

렌더 계층의 공개 façade이다. `RendererPort`를 구조적으로 구현하고 로그인/게임 장면을 선택해 같은 계층의 전용 모듈로 위임한다. `ClientApp`에는 `controls`와 `draw(...)`만 노출한다.

구체 상태·패널·네트워크·controller 모듈은 import하지 않으며 다음 포트만 입력으로 사용한다.

- `ConfigPort`
- `StatePort`
- `AnalyticsPanelPort`
- `HistoryPanelPort`

## `Renderer`

### `Renderer.__init__(self, config: ConfigPort) -> None`

```text
RenderSupport(config) 생성
RenderSupport.controls를 Renderer.controls로 공개
```

Pygame display/font 초기화는 기존대로 `ClientApp.run`이 먼저 수행한다.

### `Renderer.draw(self, state: StatePort, analytics_panel: AnalyticsPanelPort, history_panel: HistoryPanelPort) -> None`

```text
배경 지우기
state.authenticated이면 render_game.draw_game 호출
아니면 render_login.draw_login 호출
pygame.display.flip()으로 한 번만 frame 표시
```

상태와 패널 객체는 읽기만 하며 변경하지 않는다.

## 호출 관계

```text
ClientApp -> RendererPort
             -> render.Renderer
                -> render_support.RenderSupport
                -> render_login.draw_login
                -> render_game.draw_game
```

세부 책임은 다음 문서를 따른다.

- [`render_support.py.md`](render_support.py.md): 자산·글꼴·배치·공통 출력
- [`render_login.py.md`](render_login.py.md): 로그인 장면
- [`render_game.py.md`](render_game.py.md): 인증 후 화면 조정
- [`render_world.py.md`](render_world.py.md): 맵과 플레이어
- [`render_panels.py.md`](render_panels.py.md): API·통계·이력 패널
