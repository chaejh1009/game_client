"""Public RendererPort implementation and render-scene coordinator."""
from ports import AnalyticsPanelPort, ConfigPort, HistoryPanelPort, StatePort
from render_game import draw_game
from render_login import draw_login
from render_support import BG, RenderSupport


class Renderer:
    """Keep the application's render boundary stable while delegating scene work."""

    def __init__(self, config: ConfigPort) -> None:
        self._view = RenderSupport(config)
        self.controls = self._view.controls

    def draw(self, state: StatePort, analytics_panel: AnalyticsPanelPort,
             history_panel: HistoryPanelPort) -> None:
        if not state.authenticated:
            self._view.scroll_y = 0
        self._view.screen.fill(BG)
        if state.authenticated:
            draw_game(self._view, state, analytics_panel, history_panel)
        else:
            draw_login(self._view, state)
        self._view.present(show_scroll=state.authenticated)

    def resize(self, width: int, height: int) -> None:
        self._view.resize(width, height)

    def scroll(self, amount: int) -> None:
        self._view.scroll(amount)

    def pointer_to_content(self, pos: tuple[int, int]) -> tuple[int, int]:
        return self._view.pointer_to_content(pos)

    def text_input_rect(self, name: str):
        return self._view.text_input_rect(name)
