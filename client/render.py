"""Main-thread-only pygame asset preparation and rendering."""
import json
import pygame

BG = (17, 25, 35)
CARD = (27, 39, 51)
INK = (230, 238, 238)
MUTED = (155, 178, 186)
ACCENT = (107, 218, 174)
PENDING = (241, 190, 83)
ERROR = (235, 112, 112)
GRASS_FALLBACK = (92, 154, 78)
PATH_FALLBACK = (206, 158, 99)
TILE_SIZE = 32
MAP_COLUMNS = 20
MAP_ROWS = 15
CONFIRMED_IMAGE_SIZE = (16, 16)


class Renderer:
    def __init__(self, config):
        self.config = config
        self.screen = pygame.display.set_mode((config.window_width, config.window_height))
        pygame.display.set_caption('Village Lab · 로컬 접속기')
        self.asset_errors = []
        self._prepare_fonts()
        self._prepare_assets()

        width = config.window_width
        self.map_rect = pygame.Rect(24, 128, MAP_COLUMNS * TILE_SIZE, MAP_ROWS * TILE_SIZE)
        sidebar_x = self.map_rect.right + 24
        self.slots = {
            'village-board': pygame.Rect(sidebar_x, 128, width - sidebar_x - 24, 96),
            'lobby-banner': pygame.Rect(sidebar_x, 236, width - sidebar_x - 24, 96),
        }
        self.controls = {
            'username': pygame.Rect(40, 167, width - 80, 44),
            'password': pygame.Rect(40, 246, width - 80, 44),
            'login': pygame.Rect(40, 316, 180, 44),
            'up': pygame.Rect(sidebar_x + 86, 346, 76, 40),
            'left': pygame.Rect(sidebar_x, 394, 76, 40),
            'down': pygame.Rect(sidebar_x + 86, 394, 76, 40),
            'right': pygame.Rect(sidebar_x + 172, 394, 76, 40),
            'refresh': pygame.Rect(sidebar_x, 442, 76, 40),
            'logout': pygame.Rect(sidebar_x + 86, 442, 76, 40),
            'gather': pygame.Rect(sidebar_x + 172, 442, 76, 40),
        }
        self.api_panel = pygame.Rect(sidebar_x, 548, width - sidebar_x - 24,
                                     config.window_height - 572)

    def _prepare_fonts(self):
        font_path = self.config.font_path
        if font_path is None or not font_path.is_file():
            self.asset_errors.append('font_path를 client/config.json에 지정하세요.')
            font_path = pygame.font.match_font(
                'applesdgothicneo,malgungothic,nanumgothic,notosanscjkkr')
        try:
            self.font = pygame.font.Font(str(font_path) if font_path else None, 19)
            self.small = pygame.font.Font(str(font_path) if font_path else None, 14)
            self.title = pygame.font.Font(str(font_path) if font_path else None, 30)
        except (OSError, pygame.error):
            self.asset_errors.append('font_path의 폰트를 열 수 없습니다.')
            self.font = pygame.font.Font(None, 19)
            self.small = pygame.font.Font(None, 14)
            self.title = pygame.font.Font(None, 30)

    def _prepare_assets(self):
        paths = {
            'grass': self.config.grass_path,
            'path': self.config.path_path,
            'tree': self.config.tree_path,
            'house': self.config.house_path,
            'hero': self.config.hero_path,
        }
        self.assets = {}
        for name, path in paths.items():
            try:
                image = pygame.image.load(path).convert_alpha()
                if image.get_size() != CONFIRMED_IMAGE_SIZE:
                    raise ValueError('unexpected image size')
                self.assets[name] = pygame.transform.scale(image, (TILE_SIZE, TILE_SIZE))
            except (OSError, ValueError, pygame.error):
                self.assets[name] = None
                self.asset_errors.append(f'{name} 이미지 로딩 실패')

    def text(self, value, pos, color=INK, font=None):
        self.screen.blit((font or self.font).render(str(value), True, color), pos)

    def wrapped(self, value, x, y, width, font=None, color=MUTED):
        font = font or self.small
        line = ''
        for char in str(value):
            if line and font.size(line + char)[0] > width:
                self.text(line, (x, y), color, font)
                y += font.get_linesize()
                line = ''
            line += char
        self.text(line, (x, y), color, font)
        return y + font.get_linesize()

    def button(self, name, label, disabled=False, color=None):
        rect = self.controls[name]
        fill = (52, 68, 77) if disabled else (color or ACCENT)
        pygame.draw.rect(self.screen, fill, rect, border_radius=7)
        rendered = self.small.render(label, True, MUTED if disabled else BG)
        self.screen.blit(rendered, rendered.get_rect(center=rect.center))

    def _command_color(self, state, action, direction=''):
        selected = state.selected_action == action
        if action == 'move':
            selected = selected and state.selected_direction == direction
        colors = {'pending': PENDING, 'success': ACCENT, 'error': ERROR}
        return selected, colors.get(state.command_status, ACCENT) if selected else (84, 113, 122)

    def _draw_commands(self, state):
        for name, label in (('up', '↑'), ('left', '←'), ('down', '↓'), ('right', '→')):
            selected, color = self._command_color(state, 'move', name)
            disabled = state.busy or state.closing or (state.command_pending and not selected)
            self.button(name, label, disabled, color)
        selected, color = self._command_color(state, 'gather')
        disabled = state.busy or state.closing or (state.command_pending and not selected)
        self.button('gather', 'Z 채굴', disabled, color)
        disabled = state.busy or state.closing or state.command_pending
        self.button('refresh', '새로고침', disabled)
        self.button('logout', '로그아웃', disabled)

    def _draw_slot(self, name):
        rect = self.slots[name]
        pygame.draw.rect(self.screen, CARD, rect, border_radius=10)
        label = self.small.render('소식 준비 중', True, INK)
        self.screen.blit(label, label.get_rect(center=rect.center))

    def _draw_tile(self, name, x, y, fallback):
        rect = pygame.Rect(self.map_rect.x + x * TILE_SIZE,
                           self.map_rect.y + y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        image = self.assets.get(name)
        if image is None:
            pygame.draw.rect(self.screen, fallback, rect)
        else:
            self.screen.blit(image, rect)
        return rect

    def _draw_sprite_at_tile(self, name, x, y, fallback):
        tile = pygame.Rect(self.map_rect.x + x * TILE_SIZE,
                           self.map_rect.y + y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        image = self.assets.get(name)
        if image is None:
            pygame.draw.rect(self.screen, fallback, tile.inflate(-8, -5), border_radius=4)
        else:
            # The sprite's feet, not its top, define the server's logical tile.
            target = image.get_rect(midbottom=(tile.centerx, tile.bottom))
            self.screen.blit(image, target)

    def _draw_map(self, state):
        old_clip = self.screen.get_clip()
        self.screen.set_clip(self.map_rect)
        path_tiles = ({(x, 2) for x in range(MAP_COLUMNS)} |
                      {(2, y) for y in range(MAP_ROWS)})
        for y in range(MAP_ROWS):
            for x in range(MAP_COLUMNS):
                name = 'path' if (x, y) in path_tiles else 'grass'
                fallback = PATH_FALLBACK if name == 'path' else GRASS_FALLBACK
                self._draw_tile(name, x, y, fallback)

        gather = pygame.Rect(self.map_rect.x + 2 * TILE_SIZE,
                             self.map_rect.y + 2 * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        pygame.draw.rect(self.screen, PENDING, gather, width=2)

        # Decorations never alter movement or the server's collision rules.
        for x, y in ((5, 4), (12, 3), (16, 10), (8, 12)):
            self._draw_sprite_at_tile('tree', x, y, (35, 104, 60))
        for x, y in ((7, 6), (14, 8)):
            self._draw_sprite_at_tile('house', x, y, (156, 91, 69))

        own_id = state.player['player_id'] if state.player is not None else None
        players = sorted(state.players.values(), key=lambda item: item['player_id'] == own_id)
        for player in players:
            is_own = player['player_id'] == own_id
            fallback = (76, 106, 190) if is_own else (214, 116, 86)
            self._draw_sprite_at_tile('hero', player['x'], player['y'], fallback)
            tile_x = self.map_rect.x + player['x'] * TILE_SIZE
            tile_y = self.map_rect.y + player['y'] * TILE_SIZE
            marker = ACCENT if is_own else PENDING
            pygame.draw.circle(self.screen, marker, (tile_x + TILE_SIZE - 5, tile_y + 5), 4)
            label = self.small.render(str(player['player_id']), True, marker)
            self.screen.blit(label, (tile_x + 2, tile_y + 1))
        pygame.draw.rect(self.screen, (10, 18, 24), self.map_rect, width=2)
        self.screen.set_clip(old_clip)

    def _draw_command_status(self, state):
        statuses = {'pending': '요청 중', 'success': '완료', 'error': '실패'}
        colors = {'pending': PENDING, 'success': ACCENT, 'error': ERROR}
        if state.selected_action == 'gather':
            label = '코인 채굴'
        elif state.selected_direction:
            names = {'up': '위쪽', 'down': '아래쪽', 'left': '왼쪽', 'right': '오른쪽'}
            label = f'{names[state.selected_direction]} 이동'
        else:
            label = '방향키 이동 · Z 채굴'
        status = statuses.get(state.command_status)
        if status:
            label += f' · {status}'
        color = colors.get(state.command_status, MUTED)
        x = self.slots['village-board'].x
        width = self.slots['village-board'].width
        self.wrapped(label, x, 492, width, color=color)
        self.wrapped(state.message, x, 518, width, color=MUTED)

    def _draw_api_panel(self, state):
        pygame.draw.rect(self.screen, CARD, self.api_panel, border_radius=10)
        x, y = self.api_panel.x + 12, self.api_panel.y + 10
        self.text('서버 state', (x, y), ACCENT, self.small)
        self.text('status: ' + str(state.api_status or '—'), (x, y + 24), MUTED, self.small)
        data = (json.dumps(state.player, ensure_ascii=False)
                if state.player is not None else '아직 state가 없습니다.')
        self.wrapped(data, x, y + 48, self.api_panel.width - 24, color=INK)
        if self.asset_errors:
            self.wrapped(' · '.join(self.asset_errors), x, self.api_panel.bottom - 34,
                         self.api_panel.width - 24, color=ERROR)

    def _draw_game(self, state):
        self.text('작은 마을', (24, 24), font=self.title)
        player = state.player
        if player is not None:
            stats = (f"room {player['room_id']}  ·  위치 ({player['x']}, {player['y']})"
                     f"  ·  coins {player['coins']}  ·  version {player['version']}")
            self.text(stats, (24, 76), MUTED, self.small)
        self.text('채굴 지점 (2, 2)', (24, 102), PENDING, self.small)
        self._draw_map(state)
        self._draw_slot('village-board')
        self._draw_slot('lobby-banner')
        self.wrapped(f'접속 중인 플레이어 {len(state.players)}명',
                     self.slots['lobby-banner'].x + 12,
                     self.slots['lobby-banner'].y + 12,
                     self.slots['lobby-banner'].width - 24, color=INK)
        self._draw_commands(state)
        self._draw_command_status(state)
        self._draw_api_panel(state)

    def _draw_login(self, state):
        self.text('VILLAGE LAB', (40, 28), ACCENT, self.small)
        self.text('마을에 접속하기', (40, 54), font=self.title)
        self.text(self.config.server_base_url, (40, 100), MUTED, self.small)
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
            self.screen.blit(rendered,
                             (min(rect.x + 12, rect.right - 12 - rendered.get_width()), rect.y + 11))
            self.screen.set_clip(previous)
        self.button('login', '접속 중…' if state.busy else '접속', state.busy or state.closing)
        self.text('Tab 이동 · Enter 접속', (240, 329), MUTED, self.small)
        self.wrapped(state.message, 40, 377, self.config.window_width - 80)
        if self.asset_errors:
            self.wrapped(' · '.join(self.asset_errors), 40, 410,
                         self.config.window_width - 80, color=ERROR)

    def draw(self, state):
        self.screen.fill(BG)
        if state.authenticated:
            self._draw_game(state)
        else:
            self._draw_login(state)
        pygame.display.flip()
