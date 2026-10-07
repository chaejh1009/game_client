"""Pygame lifecycle and the main-thread application event loop."""
import os
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import time
from queue import Empty
from typing import Any

import pygame

from messages import Request
from ports import (AdsPanelPort, AnalyticsPanelPort, ConfigPort, ControllerPort, HistoryPanelPort,
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
                 renderer_factory: RendererFactoryPort,
                 ads_panel: AdsPanelPort | None = None,
                 lobby_ads_panel: AdsPanelPort | None = None):
        self.ads_panel = ads_panel
        self.lobby_ads_panel = lobby_ads_panel
        self._minimized = False
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
            'load_refresh', 'metrics_refresh',
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
        pos = renderer.pointer_to_content(event.pos)
        ad_target = renderer.controls.get('ad_click')
        if (self.ads_panel is not None and self.state.authenticated
                and not self.analytics_panel.visible and not self.history_panel.visible
                and renderer.ads_visible() and ad_target is not None
                and ad_target.collidepoint(pos)):
            self.controller.request_ad_event(self.ads_panel, 'click')
            return
        for name in self._control_names():
            if not renderer.controls[name].collidepoint(pos):
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
            elif name in ('load_refresh', 'metrics_refresh'):
                self.controller.request_measurement(name.removesuffix('_refresh'))
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
        elif event.type in (pygame.WINDOWMINIMIZED, pygame.WINDOWHIDDEN):
            self._minimized = True
        elif event.type in (pygame.WINDOWRESTORED, pygame.WINDOWSHOWN):
            self._minimized = False
        elif event.type == pygame.VIDEORESIZE:
            renderer.resize(event.w, event.h)
        elif event.type == pygame.MOUSEWHEEL and self.state.authenticated:
            renderer.scroll(-event.y * 72)
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
                result = self.worker.get_result_nowait()
                if result.kind in ('ad_event', 'ad_event_error'):
                    if result.needs_login:
                        self.controller.apply_result(result)
                        for panel in (self.ads_panel, self.lobby_ads_panel):
                            if panel is not None:
                                panel.clear()
                    elif (self.ads_panel is not None and self.state.authenticated
                          and not self.state.closing):
                        self.ads_panel.apply_event(result, time.monotonic())
                elif result.kind.startswith('ads_'):
                    if (not self.state.closing and
                            (result.slot_id == 'lobby-banner') != self.state.authenticated):
                        panel = (self.lobby_ads_panel if result.slot_id == 'lobby-banner'
                                 else self.ads_panel)
                        if panel is not None:
                            panel.apply(result, time.monotonic())
                else:
                    self.controller.apply_result(result)
                    if result.needs_login or result.kind in ('logged_out', 'fatal'):
                        for panel in (self.ads_panel, self.lobby_ads_panel):
                            if panel is not None:
                                panel.clear()
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
                    pygame.key.set_text_input_rect(renderer.text_input_rect(self.state.focus))
                if self.ads_panel is not None or self.lobby_ads_panel is not None:
                    active = not self.state.closing and not self._minimized
                    visible = (active and self.state.authenticated
                               and renderer.ads_visible()
                               and not self.analytics_panel.visible and not self.history_panel.visible)
                    lobby_visible = (active and not self.state.authenticated
                                     and renderer.ads_visible('lobby-banner'))
                    for panel in (self.ads_panel, self.lobby_ads_panel):
                        if panel is not None and panel.begin(time.monotonic(),
                                lobby_visible if panel.slot_id == 'lobby-banner' else visible):
                            self.worker.submit(Request('ads', request_id=panel.request_id,
                                                       slot_id=panel.slot_id))
                    args = (self.state, self.analytics_panel, self.history_panel,
                            self.ads_panel if visible else None)
                    if self.lobby_ads_panel is not None:
                        renderer.draw(*args, self.lobby_ads_panel if lobby_visible else None)
                    else:
                        renderer.draw(*args)
                else:
                    renderer.draw(self.state, self.analytics_panel, self.history_panel)
                # Renderer.draw marks displayed only after present()/display.flip().
                if (self.ads_panel is not None and self.state.authenticated
                        and not self.state.closing and not self._minimized
                        and renderer.ads_visible()
                        and not self.analytics_panel.visible and not self.history_panel.visible):
                    self.controller.request_ad_event(self.ads_panel, 'impression')
                    if self.ads_panel.click_requested:
                        self.controller.request_ad_event(self.ads_panel, 'click')
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
