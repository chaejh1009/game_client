"""Login-scene drawing for the pygame client."""
import pygame

from ports import StatePort
from render_support import ACCENT, CARD, ERROR, INK, MUTED, RenderSupport


def draw_login(view: RenderSupport, state: StatePort) -> None:
    """Draw the unauthenticated scene without mutating application state."""
    view.text('VILLAGE LAB', (240, 48), ACCENT, view.small)
    view.text('마을에 접속하기', (240, 74), font=view.title)
    view.text(view.config.server_base_url, (240, 120), MUTED, view.small)
    for name, label in (('username', '사용자명'), ('password', '비밀번호')):
        rect = view.controls[name]
        view.text(label, (rect.x, rect.y - 25), MUTED, view.small)
        pygame.draw.rect(view.screen, CARD, rect, border_radius=8)
        pygame.draw.rect(
            view.screen,
            ACCENT if state.focus == name else (54, 73, 86),
            rect,
            width=2,
            border_radius=8,
        )
        previous = view.screen.get_clip()
        view.screen.set_clip(rect.inflate(-20, -8))
        value = state.username if name == 'username' else '*' * len(state.password)
        rendered = view.font.render(value, True, INK)
        view.screen.blit(
            rendered,
            (min(rect.x + 12, rect.right - 12 - rendered.get_width()), rect.y + 11),
        )
        view.screen.set_clip(previous)
    view.button('login', '접속 중…' if state.busy else '접속', state.busy or state.closing)
    view.text('Tab 이동 · Enter 접속', (440, 329), MUTED, view.small)
    view.wrapped(state.message, 240, 377, 480)
    if view.asset_errors:
        view.wrapped(
            ' · '.join(view.asset_errors),
            240,
            410,
            480,
            color=ERROR,
        )
