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
        return (
            'up', 'down', 'left', 'right', 'gather', 'refresh', 'logout',
            'delivery', 'train', 'api_player', 'api_history', 'analytics',
            'history_panel',
        )

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
