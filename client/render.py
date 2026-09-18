"""Public RendererPort implementation and render-scene coordinator."""
import pygame

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
        self._view.screen.fill(BG)
        if state.authenticated:
            draw_game(self._view, state, analytics_panel, history_panel)
        else:
            draw_login(self._view, state)
        pygame.display.flip()
