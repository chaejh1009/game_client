"""Run from village_lab: python client/main.py"""
import os
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
from queue import Empty
import pygame
from network import NetworkWorker
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
    try:
        renderer = Renderer(config)
        worker = NetworkWorker(config.server_base_url)
        worker.start()
        clock = pygame.time.Clock()
        pygame.key.start_text_input()

        def submit(kind):
            if state.busy or state.closing:
                return
            if kind == 'login':
                if not state.username.strip() or not state.password:
                    state.message = '사용자명과 비밀번호를 입력하세요.'
                    return
                request = Request(kind, state.username.strip(), state.password)
                state.password = ''  # Drop the input field immediately; never persist it.
            else:
                request = Request(kind)
            state.busy = True
            state.message = '서버에 요청 중…'
            worker.submit(request)

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT and not state.closing:
                    state.closing = True
                    state.password = ''
                    state.message = '연결을 정리하고 종료하는 중…'
                    worker.stop()
                elif not state.closing and not state.busy:
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        names = ('refresh', 'logout') if state.authenticated else ('username', 'password', 'login')
                        for name in names:
                            if renderer.controls[name].collidepoint(event.pos):
                                if name in ('username', 'password'):
                                    state.focus = name
                                else:
                                    submit('player' if name == 'refresh' else name)
                    elif not state.authenticated and event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_TAB:
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
                    state.apply(worker.results.get_nowait())
                except Empty:
                    break
            if state.closing and not worker.thread.is_alive():
                worker.thread.join()  # Already terminated: no network waiting on UI thread.
                break
            if not state.authenticated and not state.busy and not state.closing:
                pygame.key.set_text_input_rect(renderer.controls[state.focus])
            renderer.draw(state)
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
