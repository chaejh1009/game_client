"""Pygame lifecycle and the main-thread application event loop."""
import os
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from queue import Empty
from typing import Any

import pygame

from ports import (AnalyticsPanelPort, ConfigPort, ControllerPort, HistoryPanelPort,
                   NetworkPort, RendererFactoryPort, RendererPort, StatePort)


KEY_DIRECTIONS = {
    pygame.K_UP: 'up',
    pygame.K_DOWN: 'down',
    pygame.K_LEFT: 'left',
    pygame.K_RIGHT: 'right',
}


class ClientApp:
    def __init__(self, config: ConfigPort, state: StatePort,
                 analytics_panel: AnalyticsPanelPort, history_panel: HistoryPanelPort,
                 worker: NetworkPort, controller: ControllerPort,
                 renderer_factory: RendererFactoryPort):
        self.config = config
        self.state = state
        self.analytics_panel = analytics_panel
        self.history_panel = history_panel
        self.worker = worker
        self.controller = controller
        self.renderer_factory = renderer_factory

    def _control_names(self) -> tuple[str, ...]:
        if not self.state.authenticated:
            return ('username', 'password', 'login')
        names = (
            'up', 'down', 'left', 'right', 'gather', 'refresh', 'logout',
            'delivery', 'train', 'api_player', 'api_history', 'api_windows',
            'api_analytics', 'analytics',
            'history_panel',
        )
        panel = self.analytics_panel
        if panel.visible:
            names += ('analytics_summary', 'analytics_windows')
            idle = not (panel.pending or panel.ingest_pending or panel.windows_pending)
            if panel.analytics_view == 'windows':
                names += ('windows_all', 'windows_tumbling', 'windows_sliding')
                if idle:
                    names += ('windows_refresh',)
                if panel.window_page > 0:
                    names += ('windows_previous',)
                if panel.window_page + 1 < panel.window_page_count:
                    names += ('windows_next',)
            elif idle:
                names += ('ingest_refresh',)
                names += ('analytics_refresh',)
        return names

    def _handle_mouse(self, event: Any, renderer: RendererPort) -> None:
        for name in self._control_names():
            if not renderer.controls[name].collidepoint(event.pos):
                continue
            if name in ('username', 'password'):
                self.state.focus = name
            elif name in ('up', 'down', 'left', 'right'):
                self.controller.request_command('move', name)
            elif name == 'gather':
                self.controller.request_command('gather')
            elif name == 'train':
                self.controller.request_command('train')
            elif name == 'delivery':
                self.controller.request_delivery()
            elif name == 'analytics':
                self.controller.toggle_analytics()
            elif name in ('analytics_refresh', 'api_analytics'):
                self.controller.request_analytics()
            elif name == 'ingest_refresh':
                self.controller.request_ingest()
            elif name in ('windows_refresh', 'api_windows'):
                self.controller.request_windows()
            elif name in ('analytics_summary', 'analytics_windows'):
                self.controller.select_analytics_view(name.removeprefix('analytics_'))
            elif name in ('windows_all', 'windows_tumbling', 'windows_sliding'):
                self.controller.select_window_kind(name.removeprefix('windows_'))
            elif name in ('windows_previous', 'windows_next'):
                self.controller.change_window_page(-1 if name == 'windows_previous' else 1)
            elif name == 'history_panel':
                self.controller.toggle_history()
            elif name == 'api_player':
                self.controller.submit('player')
            elif name == 'api_history':
                self.controller.request_history()
            else:
                self.controller.submit('player' if name == 'refresh' else name)

    def _handle_keydown(self, event: Any) -> None:
        if self.state.authenticated:
            direction = KEY_DIRECTIONS.get(event.key)
            if direction is not None:
                self.controller.request_command('move', direction)
            elif event.key == pygame.K_z:
                self.controller.request_command('gather')
            elif event.key == pygame.K_x:
                self.controller.request_command('train')
        elif event.key == pygame.K_TAB:
            self.state.focus = 'password' if self.state.focus == 'username' else 'username'
        elif event.key == pygame.K_BACKSPACE:
            setattr(self.state, self.state.focus, getattr(self.state, self.state.focus)[:-1])
        elif event.key == pygame.K_RETURN:
            self.controller.submit('login')

    def _handle_event(self, event: Any, renderer: RendererPort) -> None:
        if event.type == pygame.QUIT and not self.state.closing:
            self.controller.begin_shutdown()
        elif not self.state.closing and not self.state.busy:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_mouse(event, renderer)
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event)
            elif not self.state.authenticated and event.type == pygame.TEXTINPUT:
                value = getattr(self.state, self.state.focus)
                limit = 150 if self.state.focus == 'username' else 256
                value += ''.join(char for char in event.text if char.isprintable())
                setattr(self.state, self.state.focus, value[:limit])

    def _drain_results(self) -> None:
        while True:
            try:
                self.controller.apply_result(self.worker.get_result_nowait())
            except Empty:
                return

    def run(self) -> int:
        pygame.display.init()
        pygame.font.init()
        try:
            renderer = self.renderer_factory(self.config)
            self.worker.start()
            clock = pygame.time.Clock()
            pygame.key.start_text_input()

            while True:
                for event in pygame.event.get():
                    self._handle_event(event, renderer)
                self._drain_results()
                if self.state.closing and not self.worker.is_alive():
                    self.worker.join()  # Already terminated: no network wait on UI thread.
                    break
                if not self.state.authenticated and not self.state.busy and not self.state.closing:
                    pygame.key.set_text_input_rect(renderer.controls[self.state.focus])
                renderer.draw(self.state, self.analytics_panel, self.history_panel)
                clock.tick(60)
        finally:
            self.state.password = ''
            if self.worker.is_alive():
                self.worker.stop()
                # Keep SDL responsive during exceptional shutdown; never join a live worker.
                while self.worker.is_alive():
                    pygame.event.pump()
                    pygame.time.Clock().tick(60)
                self.worker.join()
            pygame.key.stop_text_input()
            pygame.quit()
        return 0
