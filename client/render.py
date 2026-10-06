"""Public RendererPort implementation and render-scene coordinator."""
import time
import pygame

from ports import AdsPanelPort, AnalyticsPanelPort, ConfigPort, HistoryPanelPort, StatePort
from render_ads import AdsRenderer
from render_game import draw_game
from render_login import draw_login
from render_support import BG, RenderSupport


class Renderer:
    """Keep the application's render boundary stable while delegating scene work."""

    def __init__(self, config: ConfigPort) -> None:
        self._view = RenderSupport(config)
        self._ads = AdsRenderer()
        self.controls = self._view.controls

    def draw(self, state: StatePort, analytics_panel: AnalyticsPanelPort,
             history_panel: HistoryPanelPort,
             ads_panel: AdsPanelPort | None = None) -> None:
        if not state.authenticated:
            self._view.scroll_y = 0
        self._view.screen.fill(BG)
        if state.authenticated:
            draw_game(self._view, state, analytics_panel, history_panel)
        else:
            draw_login(self._view, state)
        ad_blitted = False
        if (ads_panel is not None and state.authenticated and not state.closing
                and not analytics_panel.visible and not history_panel.visible
                and self.ads_visible()):
            ad_blitted = self._ads.draw(self._view, ads_panel)
        self._view.present(show_scroll=state.authenticated)
        if ad_blitted:
            ads_panel.mark_displayed(time.monotonic())

    def resize(self, width: int, height: int) -> None:
        self._view.resize(width, height)

    def scroll(self, amount: int) -> None:
        self._view.scroll(amount)

    def pointer_to_content(self, pos: tuple[int, int]) -> tuple[int, int]:
        return self._view.pointer_to_content(pos)

    def text_input_rect(self, name: str):
        return self._view.text_input_rect(name)

    def ads_visible(self) -> bool:
        if not self._view.display or not pygame.display.get_active():
            return False
        _scale, _left, height = self._view._viewport()
        rect = self._view.ad_rect
        return self._view.scroll_y <= rect.top and rect.bottom <= self._view.scroll_y + height
