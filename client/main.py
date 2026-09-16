"""Run from village_lab: python client/main.py"""
import os
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
from queue import Empty
import time
import pygame
from network import NetworkWorker
from panels import AnalyticsPanelState, HistoryPanelState
from render import Renderer
from state import Config, Request, State


def main():
    try:
        config = Config.load()
    except (OSError, ValueError, TypeError, AttributeError):
        print('client/config.json 설정을 확인하세요. origin, 창 크기, 타일 크기, 자산 경로가 필요합니다.')
        return 1
    pygame.display.init()
    pygame.font.init()
    worker = None
    state = State()
    analytics_panel = AnalyticsPanelState()
    history_panel = HistoryPanelState()
    try:
        renderer = Renderer(config)
        worker = NetworkWorker(config.server_base_url)
        worker.start()
        clock = pygame.time.Clock()
        pygame.key.start_text_input()

        def submit(kind):
            if state.busy or state.closing or state.command_pending:
                return False
            if kind in ('player', 'history', 'logout') and (state.delivery_pending
                                                             or analytics_panel.pending
                                                             or history_panel.pending):
                return False
            if kind == 'login':
                if not state.username.strip() or not state.password:
                    state.message = '사용자명과 비밀번호를 입력하세요.'
                    return False
                request = Request(kind, state.username.strip(), state.password)
                analytics_panel.clear()
                history_panel.clear()
                state.password = ''  # Drop the input field immediately; never persist it.
            else:
                request = Request(kind)
            state.busy = True
            state.message = '서버에 요청 중…'
            worker.submit(request)
            return True

        def request_command(action, direction=''):
            # Keyboard and mouse deliberately share this gate and request path.
            if state.begin_command(action, time.monotonic(), direction):
                if action == 'train':
                    history_panel.wait_for_train()
                worker.submit(Request('command', direction=direction, action=action))

        def request_delivery():
            if state.begin_delivery(time.monotonic()):
                worker.submit(Request('delivery'))

        def toggle_analytics():
            if analytics_panel.visible:
                analytics_panel.hide()
            elif analytics_panel.begin(state.authenticated, state.closing):
                history_panel.hide()
                worker.submit(Request('analytics'))

        def toggle_history():
            if history_panel.visible:
                history_panel.hide()
            elif not analytics_panel.pending:
                analytics_panel.hide()
                history_panel.show()

        def request_history():
            if not history_panel.pending and submit('history'):
                history_panel.begin()
                analytics_panel.hide()

        key_directions = {
            pygame.K_UP: 'up',
            pygame.K_DOWN: 'down',
            pygame.K_LEFT: 'left',
            pygame.K_RIGHT: 'right',
        }

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT and not state.closing:
                    state.closing = True
                    state.password = ''
                    state.message = '연결을 정리하고 종료하는 중…'
                    worker.stop()
                elif not state.closing and not state.busy:
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        names = (('up', 'down', 'left', 'right', 'gather', 'refresh',
                                  'logout', 'delivery', 'train', 'api_player', 'api_history')
                                 + (('analytics', 'history_panel') if state.authenticated else ())
                                 if state.authenticated else ('username', 'password', 'login'))
                        for name in names:
                            if renderer.controls[name].collidepoint(event.pos):
                                if name in ('username', 'password'):
                                    state.focus = name
                                elif name in ('up', 'down', 'left', 'right'):
                                    request_command('move', name)
                                elif name == 'gather':
                                    request_command('gather')
                                elif name == 'train':
                                    request_command('train')
                                elif name == 'delivery':
                                    request_delivery()
                                elif name == 'analytics':
                                    toggle_analytics()
                                elif name == 'history_panel':
                                    toggle_history()
                                elif name == 'api_player':
                                    submit('player')
                                elif name == 'api_history':
                                    request_history()
                                else:
                                    submit('player' if name == 'refresh' else name)
                    elif event.type == pygame.KEYDOWN:
                        if state.authenticated:
                            direction = key_directions.get(event.key)
                            if direction is not None:
                                request_command('move', direction)
                            elif event.key == pygame.K_z:
                                request_command('gather')
                            elif event.key == pygame.K_x:
                                request_command('train')
                        elif event.key == pygame.K_TAB:
                            state.focus = 'password' if state.focus == 'username' else 'username'
                        elif event.key == pygame.K_BACKSPACE:
                            setattr(state, state.focus, getattr(state, state.focus)[:-1])
                        elif event.key == pygame.K_RETURN:
                            submit('login')
                    elif not state.authenticated and event.type == pygame.TEXTINPUT:
                        value = getattr(state, state.focus)
                        limit = 150 if state.focus == 'username' else 256
                        value += ''.join(c for c in event.text if c.isprintable())
                        setattr(state, state.focus, value[:limit])
            while True:
                try:
                    result = worker.results.get_nowait()
                    handled = analytics_panel.apply(result)
                    history_handled = history_panel.apply(result)
                    if not (handled or history_handled) or result.needs_login:
                        state.apply(result)
                    if result.kind == 'logged_out' or result.needs_login:
                        analytics_panel.clear()
                        history_panel.clear()
                except Empty:
                    break
            if state.closing and not worker.thread.is_alive():
                worker.thread.join()  # Already terminated: no network waiting on UI thread.
                break
            if not state.authenticated and not state.busy and not state.closing:
                pygame.key.set_text_input_rect(renderer.controls[state.focus])
            renderer.draw(state, analytics_panel, history_panel)
            clock.tick(60)
    finally:
        state.password = ''
        if worker is not None and worker.thread.is_alive():
            worker.stop()
            # Keep SDL responsive even during exceptional shutdown; never join a live worker.
            while worker.thread.is_alive():
                pygame.event.pump()
                pygame.time.Clock().tick(60)
            worker.thread.join()
        pygame.key.stop_text_input()
        pygame.quit()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
