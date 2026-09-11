"""All pygame calls, including optional asset decoding, stay on the main thread."""
import json
import pygame
from state import PLAYER_FIELDS

BG = (17, 25, 35)
CARD = (27, 39, 51)
INK = (230, 238, 238)
MUTED = (155, 178, 186)
ACCENT = (107, 218, 174)

class Renderer:
    def __init__(self, config):
        self.config = config
        self.screen = pygame.display.set_mode((config.window_width, config.window_height))
        pygame.display.set_caption('Village Lab · 로컬 접속기')
        font_file = config.assets_dir / 'font.ttf'
        fallback = pygame.font.match_font('applesdgothicneo,malgungothic,nanumgothic,notosanscjkkr')
        font_path = str(font_file) if font_file.is_file() else fallback
        self.font = pygame.font.Font(font_path, 19)
        self.small = pygame.font.Font(font_path, 15)
        self.title = pygame.font.Font(font_path, 30)
        w = config.window_width
        self.controls = {
            'username': pygame.Rect(40, 167, w - 80, 44),
            'password': pygame.Rect(40, 246, w - 80, 44),
            'login': pygame.Rect(40, 316, 180, 44),
            'refresh': pygame.Rect(40, 316, 180, 44),
            'logout': pygame.Rect(236, 316, 160, 44),
        }

    def text(self, text, pos, color=INK, font=None):
        self.screen.blit((font or self.font).render(str(text), True, color), pos)

    def wrapped(self, text, x, y, width, font=None, color=MUTED):
        font = font or self.small
        line = ''
        for char in text:
            if font.size(line + char)[0] > width:
                self.text(line, (x, y), color, font)
                y += font.get_linesize()
                line = ''
            line += char
        self.text(line, (x, y), color, font)
        return y + font.get_linesize()

    def button(self, name, label, disabled=False):
        rect = self.controls[name]
        pygame.draw.rect(self.screen, (52, 68, 77) if disabled else ACCENT, rect, border_radius=9)
        self.text(label, (rect.x + 15, rect.y + 10), MUTED if disabled else BG)

    def draw(self, state):
        self.screen.fill(BG)
        self.text('VILLAGE LAB', (40, 28), ACCENT, self.small)
        self.text('마을 준비 중' if state.authenticated else '마을에 접속하기', (40, 54), font=self.title)
        self.text(self.config.server_base_url, (40, 100), MUTED, self.small)
        if state.authenticated:
            pygame.draw.rect(self.screen, CARD, (32, 142, self.config.window_width - 64, 157), border_radius=12)
            for index, key in enumerate(PLAYER_FIELDS):
                column, row = index % 2, index // 2
                x = 48 + column * ((self.config.window_width - 96) // 2)
                self.text(f'{key}: {state.player[key]}', (x, 160 + row * 42))
            self.button('refresh', '상태 새로고침', state.busy or state.closing)
            self.button('logout', '로그아웃', state.busy or state.closing)
        else:
            for name, label in (('username', '사용자명'), ('password', '비밀번호')):
                rect = self.controls[name]
                self.text(label, (rect.x, rect.y - 25), MUTED, self.small)
                pygame.draw.rect(self.screen, CARD, rect, border_radius=8)
                pygame.draw.rect(self.screen, ACCENT if state.focus == name else (54, 73, 86),
                                 rect, width=2, border_radius=8)
                previous = self.screen.get_clip()
                self.screen.set_clip(rect.inflate(-20, -8))
                value = state.username if name == 'username' else '*' * len(state.password)
                rendered = self.font.render(value, True, INK)
                self.screen.blit(rendered, (min(rect.x + 12, rect.right - 12 - rendered.get_width()), rect.y + 11))
                self.screen.set_clip(previous)
            self.button('login', '접속 중…' if state.busy else '접속', state.busy or state.closing)
            self.text('Tab 이동 · Enter 접속', (240, 329), MUTED, self.small)
        self.wrapped(state.message, 40, 377, self.config.window_width - 80)
        panel = pygame.Rect(32, 430, self.config.window_width - 64, self.config.window_height - 452)
        pygame.draw.rect(self.screen, CARD, panel, border_radius=12)
        self.text('API 응답 보기 · 읽기 전용', (48, 444), ACCENT)
        self.text('GET /api/player/   |   status: ' + str(state.api_status or '—'), (48, 477), MUTED, self.small)
        data = json.dumps(state.api_json, ensure_ascii=False) if state.api_json is not None else '아직 표시할 JSON이 없습니다.'
        old = self.screen.get_clip()
        self.screen.set_clip(panel.inflate(-24, -12))
        self.wrapped(data, 48, 507, panel.width - 32, color=INK)
        self.screen.set_clip(old)
        pygame.display.flip()
