"""All pygame calls, including optional asset decoding, stay on the main thread."""
import json
import pygame
from state import PLAYER_FIELDS

BG = (17, 25, 35)
CARD = (27, 39, 51)
INK = (230, 238, 238)
MUTED = (155, 178, 186)
ACCENT = (107, 218, 174)
PENDING = (241, 190, 83)
ERROR = (235, 112, 112)

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
            'up': pygame.Rect(w // 2 - 60, 318, 120, 44),
            'left': pygame.Rect(w // 2 - 190, 370, 120, 44),
            'down': pygame.Rect(w // 2 - 60, 370, 120, 44),
            'right': pygame.Rect(w // 2 + 70, 370, 120, 44),
            'refresh': pygame.Rect(40, 458, 180, 44),
            'logout': pygame.Rect(236, 458, 160, 44),
            'gather': pygame.Rect(412, 458, 180, 44),
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

    def button(self, name, label, disabled=False, color=None):
        rect = self.controls[name]
        pygame.draw.rect(self.screen, (52, 68, 77) if disabled else (color or ACCENT),
                         rect, border_radius=9)
        self.text(label, (rect.x + 15, rect.y + 10), MUTED if disabled else BG)

    def direction_button(self, state, name, label):
        selected = state.selected_action == 'move' and state.selected_direction == name
        status_text = {'pending': '대기', 'success': '완료', 'error': '실패'}
        colors = {'pending': PENDING, 'success': ACCENT, 'error': ERROR}
        suffix = f" · {status_text[state.command_status]}" if selected else ''
        color = colors.get(state.command_status, ACCENT) if selected else (84, 113, 122)
        disabled = state.busy or state.closing or (state.command_pending and not selected)
        self.button(name, label + suffix, disabled, color)

    def gather_button(self, state):
        selected = state.selected_action == 'gather'
        status_text = {'pending': '대기', 'success': '완료', 'error': '실패'}
        colors = {'pending': PENDING, 'success': ACCENT, 'error': ERROR}
        suffix = f" · {status_text[state.command_status]}" if selected else ''
        color = colors.get(state.command_status, ACCENT) if selected else (84, 113, 122)
        disabled = state.busy or state.closing or (state.command_pending and not selected)
        self.button('gather', 'Z 코인 채굴' + suffix, disabled, color)

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
            self.direction_button(state, 'up', '↑ 위')
            self.direction_button(state, 'left', '← 왼쪽')
            self.direction_button(state, 'down', '↓ 아래')
            self.direction_button(state, 'right', '→ 오른쪽')
            names = {'up': '위쪽', 'down': '아래쪽', 'left': '왼쪽', 'right': '오른쪽'}
            statuses = {'pending': '요청 중', 'success': '완료', 'error': '실패'}
            status_colors = {'pending': PENDING, 'success': ACCENT, 'error': ERROR}
            if state.selected_action == 'gather':
                self.text(f"선택 명령: 코인 채굴 · {statuses.get(state.command_status, '선택됨')}",
                          (40, 425), status_colors.get(state.command_status, MUTED), self.small)
            elif state.selected_direction:
                self.text(f"선택 명령: {names[state.selected_direction]} 이동 · "
                          f"{statuses.get(state.command_status, '선택됨')}",
                          (40, 425), status_colors.get(state.command_status, MUTED), self.small)
            else:
                self.text('방향키 또는 이동 버튼을 선택하세요.', (40, 425), MUTED, self.small)
            self.button('refresh', '상태 새로고침', state.busy or state.closing or state.command_pending)
            self.button('logout', '로그아웃', state.busy or state.closing or state.command_pending)
            self.gather_button(state)
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
        message_y = 516 if state.authenticated else 377
        panel_y = 552 if state.authenticated else 430
        self.wrapped(state.message, 40, message_y, self.config.window_width - 80)
        panel = pygame.Rect(32, panel_y, self.config.window_width - 64,
                            self.config.window_height - panel_y - 22)
        pygame.draw.rect(self.screen, CARD, panel, border_radius=12)
        self.text('API 응답 보기 · 읽기 전용', (48, panel_y + 14), ACCENT)
        self.text('GET /api/player/   |   status: ' + str(state.api_status or '—'),
                  (48, panel_y + 47), MUTED, self.small)
        data = json.dumps(state.api_json, ensure_ascii=False) if state.api_json is not None else '아직 표시할 JSON이 없습니다.'
        old = self.screen.get_clip()
        self.screen.set_clip(panel.inflate(-24, -12))
        self.wrapped(data, 48, panel_y + 77, panel.width - 32, color=INK)
        self.screen.set_clip(old)
        pygame.display.flip()
