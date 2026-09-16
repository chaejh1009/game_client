"""Main-thread-only pygame asset preparation and rendering."""
import json
import math
import time
import pygame

BG = (17, 25, 35)
CARD = (27, 39, 51)
INK = (230, 238, 238)
MUTED = (155, 178, 186)
ACCENT = (107, 218, 174)
PENDING = (241, 190, 83)
ERROR = (235, 112, 112)
TRAIN = (113, 166, 255)
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
        sidebar_width = width - sidebar_x - 24
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
            'refresh': pygame.Rect(sidebar_x, 442, 57, 40),
            'logout': pygame.Rect(sidebar_x + 63, 442, 57, 40),
            'gather': pygame.Rect(sidebar_x + 126, 442, 57, 40),
            'train': pygame.Rect(sidebar_x + 189, 442, 59, 40),
            'delivery': pygame.Rect(sidebar_x + 130, 136, 106, 30),
            'analytics': pygame.Rect(sidebar_x, 492, (sidebar_width - 8) // 2, 36),
            'history_panel': pygame.Rect(sidebar_x + (sidebar_width - 8) // 2 + 8,
                                         492, (sidebar_width - 8) // 2, 36),
        }
        self.api_panel = pygame.Rect(sidebar_x, 548, width - sidebar_x - 24,
                                     config.window_height - 572)
        api_button_width = (self.api_panel.width - 30) // 2
        self.controls.update({
            'api_player': pygame.Rect(self.api_panel.x + 10, self.api_panel.y + 30,
                                      api_button_width, 26),
            'api_history': pygame.Rect(self.api_panel.x + 20 + api_button_width,
                                       self.api_panel.y + 30, api_button_width, 26),
        })

    def _prepare_fonts(self):
        font_path = self.config.font_path
        if font_path is None or not font_path.is_file():
            self.asset_errors.append('font_path를 client/config.json에 지정하세요.')
            font_path = pygame.font.match_font(
                'applesdgothicneo,malgungothic,nanumgothic,notosanscjkkr')
        try:
            self.font = pygame.font.Font(str(font_path) if font_path else None, 19)
            self.small = pygame.font.Font(str(font_path) if font_path else None, 14)
            self.tiny = pygame.font.Font(str(font_path) if font_path else None, 12)
            self.title = pygame.font.Font(str(font_path) if font_path else None, 30)
        except (OSError, pygame.error):
            self.asset_errors.append('font_path의 폰트를 열 수 없습니다.')
            self.font = pygame.font.Font(None, 19)
            self.small = pygame.font.Font(None, 14)
            self.tiny = pygame.font.Font(None, 12)
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

    def _draw_commands(self, state, analytics_panel=None, history_panel=None):
        for name, label in (('up', '↑'), ('left', '←'), ('down', '↓'), ('right', '→')):
            selected, color = self._command_color(state, 'move', name)
            disabled = state.busy or state.closing or (state.command_pending and not selected)
            self.button(name, label, disabled, color)
        selected, color = self._command_color(state, 'gather')
        disabled = state.busy or state.closing or (state.command_pending and not selected)
        self.button('gather', '채굴', disabled, color)
        selected, color = self._command_color(state, 'train')
        at_train_tile = (state.player is not None
                         and (state.player['x'], state.player['y']) == (3, 2))
        train_enabled = (state.authenticated and state.ws_connected and at_train_tile
                         and not state.command_pending and not state.busy
                         and not state.closing)
        self.button('train', 'X 수련', not train_enabled, color)
        disabled = (state.busy or state.closing or state.command_pending
                    or state.delivery_pending
                    or analytics_panel is not None and analytics_panel.pending)
        self.button('refresh', '갱신', disabled)
        self.button('logout', '로그아웃', disabled)

    def _draw_delivery(self, state):
        pending = state.delivery_pending
        elapsed = time.monotonic() - state.last_delivery_at
        cooling = state.last_delivery_at >= 0 and elapsed < 5.0
        if pending:
            label = '확인 중…'
        elif cooling:
            label = f'{math.ceil(5.0 - elapsed)}초 후'
        else:
            label = '전달 상태'
        self.button('delivery', label, pending or cooling or state.busy or state.closing)
        panel = self.slots['village-board']
        if state.event_count is None:
            counts = '이벤트 — · 발행 대기 —'
        else:
            counts = (f'이벤트 {state.event_count} · '
                      f'발행 대기 {state.pending_publish_count}')
        self.text(counts, (panel.x + 12, panel.y + 52), INK, self.small)
        source = state.delivery_source or '—'
        self.text(f'source: {source}', (panel.x + 12, panel.y + 73), MUTED, self.small)

    def _draw_slot(self, name):
        rect = self.slots[name]
        pygame.draw.rect(self.screen, CARD, rect, border_radius=10)

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

        train = pygame.Rect(self.map_rect.x + 3 * TILE_SIZE,
                            self.map_rect.y + 2 * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        pygame.draw.rect(self.screen, TRAIN, train, width=2)
        pygame.draw.line(self.screen, TRAIN, (train.centerx, train.y + 15),
                         (train.centerx, train.bottom - 5), 2)
        sign = pygame.Rect(train.x + 6, train.y + 6, TILE_SIZE - 12, 11)
        pygame.draw.rect(self.screen, (31, 58, 91), sign, border_radius=2)
        pygame.draw.rect(self.screen, TRAIN, sign, width=1, border_radius=2)

        # Decorations never alter movement or the server's collision rules.
        for x, y in ((5, 4), (12, 3), (16, 10), (8, 12)):
            self._draw_sprite_at_tile('tree', x, y, (35, 104, 60))
        for x, y in ((7, 6), (14, 8)):
            self._draw_sprite_at_tile('house', x, y, (156, 91, 69))

        own_id = state.my_player_id
        players = sorted(state.players.values(), key=lambda item: item['player_id'] == own_id)
        for player in players:
            is_own = player['player_id'] == own_id
            fallback = (76, 106, 190) if is_own else (214, 116, 86)
            self._draw_sprite_at_tile('hero', player['x'], player['y'], fallback)
            tile_x = self.map_rect.x + player['x'] * TILE_SIZE
            tile_y = self.map_rect.y + player['y'] * TILE_SIZE
            marker = ACCENT if is_own else PENDING
            outline = pygame.Rect(tile_x + 2, tile_y + 2, TILE_SIZE - 4, TILE_SIZE - 4)
            pygame.draw.rect(self.screen, marker, outline, width=3 if is_own else 1,
                             border_radius=5)
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
        elif state.selected_action == 'train':
            label = '개인 수련'
        elif state.selected_direction:
            names = {'up': '위쪽', 'down': '아래쪽', 'left': '왼쪽', 'right': '오른쪽'}
            label = f'{names[state.selected_direction]} 이동'
        else:
            label = '방향키 이동 · Z 채굴 · X 수련'
        status = statuses.get(state.command_status)
        if status:
            label += f' · {status}'
        color = colors.get(state.command_status, MUTED)
        self.wrapped(label, 24, 620, self.map_rect.width, color=color)
        self.wrapped(state.message, 24, 646, self.map_rect.width, color=MUTED)

    def _draw_analytics_panel(self, panel):
        if panel is None or not panel.visible:
            return
        rect = self.map_rect.inflate(-80, -70)
        pygame.draw.rect(self.screen, BG, rect, border_radius=12)
        pygame.draw.rect(self.screen, ACCENT, rect, width=2, border_radius=12)
        previous = self.screen.get_clip()
        self.screen.set_clip(rect.inflate(-4, -4))
        x, y = rect.x + 18, rect.y + 14
        self.text('확정 이벤트 통계', (x, y), ACCENT, self.font)
        if panel.pending:
            self.text('저장된 집계 결과를 읽는 중…', (x, y + 42), MUTED, self.small)
            self.screen.set_clip(previous)
            return
        if panel.available is False:
            self.text('아직 첫 집계가 없습니다', (x, y + 42), PENDING, self.font)
            self.screen.set_clip(previous)
            return
        if panel.available is not True:
            self.text(panel.message or '통계를 읽지 않았습니다.', (x, y + 42), MUTED,
                      self.small)
            self.screen.set_clip(previous)
            return
        self.text(f'전체 확정 사실 {panel.event_count}', (x, y + 36), INK, self.font)
        self.text(f'생성: {panel.generated_at}', (x, y + 64), MUTED, self.small)
        self.text(f'schema {panel.schema_version}', (rect.right - 92, y + 16), MUTED,
                  self.small)
        table_y = y + 100
        column_width = (rect.width - 54) // 2
        for index, (title, rows, label_key) in enumerate((
                ('행동별', panel.by_action, 'event_type'),
                ('방별', panel.by_room, 'room_id'))):
            column_x = x + index * (column_width + 18)
            self.text(title, (column_x, table_y), ACCENT, self.small)
            header = pygame.Rect(column_x, table_y + 24, column_width, 24)
            pygame.draw.rect(self.screen, CARD, header, border_radius=4)
            self.text('항목', (header.x + 8, header.y + 4), MUTED, self.small)
            self.text('count', (header.right - 52, header.y + 4), MUTED, self.small)
            row_y = header.bottom + 4
            for row in rows[:8]:
                row_rect = pygame.Rect(column_x, row_y, column_width, 23)
                pygame.draw.rect(self.screen, CARD, row_rect, width=1, border_radius=3)
                label = str(row[label_key])
                self.text(label[:22], (row_rect.x + 8, row_rect.y + 3), INK, self.small)
                self.text(str(row['count']), (row_rect.right - 48, row_rect.y + 3), INK,
                          self.small)
                row_y += 25
        self.screen.set_clip(previous)

    def _draw_api_panel(self, state, analytics_panel=None, history_panel=None):
        pygame.draw.rect(self.screen, CARD, self.api_panel, border_radius=10)
        previous = self.screen.get_clip()
        self.screen.set_clip(self.api_panel.inflate(-8, -8))
        x, y = self.api_panel.x + 12, self.api_panel.y + 10
        self.text('API 응답 보기', (x, y), ACCENT, self.small)
        disabled = (state.busy or state.closing or state.command_pending
                    or state.delivery_pending
                    or analytics_panel is not None and analytics_panel.pending
                    or history_panel is not None and history_panel.pending)
        self.button('api_player', '/api/player/', disabled,
                    ACCENT if state.api_path == '/api/player/' else (84, 113, 122))
        self.button('api_history', '/api/history/', disabled,
                    ACCENT if state.api_path == '/api/history/' else (84, 113, 122))
        path = state.api_path or '—'
        status = str(state.api_status) if state.api_status is not None else '—'
        self.text(f'{path} · status {status}', (x, y + 62), MUTED, self.small)
        data = (json.dumps(state.api_json, ensure_ascii=False)
                if state.api_json is not None else '아직 API 응답이 없습니다.')
        self.wrapped(data, x, y + 84, self.api_panel.width - 24, color=INK)
        self.screen.set_clip(previous)

    def _draw_history_panel(self, panel):
        if panel is None or not panel.visible:
            return
        rect = self.map_rect.inflate(-60, -44)
        pygame.draw.rect(self.screen, BG, rect, border_radius=12)
        pygame.draw.rect(self.screen, TRAIN, rect, width=2, border_radius=12)
        previous = self.screen.get_clip()
        self.screen.set_clip(rect.inflate(-4, -4))
        x, y = rect.x + 18, rect.y + 14
        self.text('최근 행동 이력', (x, y), TRAIN, self.font)
        if panel.pending:
            self.text(panel.message, (x, y + 42), MUTED, self.small)
            self.screen.set_clip(previous)
            return
        if not panel.events:
            self.text(panel.message, (x, y + 42), MUTED, self.small)
            self.screen.set_clip(previous)
            return
        self.text(f'{panel.scope} · 최대 {panel.limit}개', (x + 150, y + 5), MUTED,
                  self.small)
        header_y = y + 42
        self.text('event_time', (x, header_y), MUTED, self.tiny)
        self.text('event_type', (x + 160, header_y), MUTED, self.tiny)
        self.text('transition', (x + 300, header_y), MUTED, self.tiny)
        row_y = header_y + 18
        for event in panel.events[:20]:
            row = pygame.Rect(x, row_y, rect.width - 36, 16)
            pygame.draw.rect(self.screen, CARD, row, border_radius=4)
            event_time = str(event['event_time']).replace('T', ' ')[:19]
            self.text(event_time, (row.x + 8, row.y + 2), INK, self.tiny)
            self.text(str(event['event_type'])[:20], (row.x + 168, row.y + 2), INK,
                      self.tiny)
            transition = event['payload']['transition']
            if transition is None:
                detail = '확장 이전 기록'
                color = PENDING
            else:
                reward = transition['reward']
                detail = f"step {transition['step']} · reward {reward:+g}"
                color = ACCENT if reward >= 0 else ERROR
            self.text(detail, (row.x + 308, row.y + 2), color, self.tiny)
            row_y += 17
        self.screen.set_clip(previous)

    def _draw_game(self, state, analytics_panel=None, history_panel=None):
        self.text('작은 마을', (24, 24), font=self.title)
        player = state.player
        if player is not None:
            stats = (f"room {player['room_id']}  ·  위치 ({player['x']}, {player['y']})"
                     f"  ·  coins {player['coins']}  ·  version {player['version']}")
            self.text(stats, (24, 76), MUTED, self.small)
        self.text('채굴 지점 (2, 2)  ·  개인 수련 (3, 2)', (24, 102), PENDING,
                  self.small)
        self._draw_map(state)
        self._draw_slot('village-board')
        self._draw_slot('lobby-banner')
        room = state.room_id if state.room_id is not None else '—'
        stale = '' if state.ws_connected else ' · 마지막 정보'
        room_panel = self.slots['village-board']
        self.text(f'방 {room}', (room_panel.x + 12, room_panel.y + 10), ACCENT, self.small)
        self.wrapped(f'온라인 {state.online_count}명{stale}', room_panel.x + 12,
                     room_panel.y + 30, 112,
                     color=INK if state.ws_connected else PENDING)
        self._draw_delivery(state)
        ws_panel = self.slots['lobby-banner']
        previous = self.screen.get_clip()
        self.screen.set_clip(ws_panel.inflate(-8, -8))
        self.text('WS 메시지', (ws_panel.x + 12, ws_panel.y + 10), ACCENT, self.small)
        ws_data = (json.dumps(state.ws_json, ensure_ascii=False)
                   if state.ws_json is not None else '아직 WS 메시지가 없습니다.')
        self.wrapped(ws_data, ws_panel.x + 12, ws_panel.y + 34,
                     ws_panel.width - 24, color=INK)
        self.screen.set_clip(previous)
        self._draw_commands(state, analytics_panel, history_panel)
        label = ('통계 닫기' if analytics_panel is not None and analytics_panel.visible
                 else '통계 읽기')
        disabled = (analytics_panel is not None and analytics_panel.pending)
        self.button('analytics', label, disabled or state.busy or state.closing)
        history_label = ('이력 닫기' if history_panel is not None and history_panel.visible
                         else '수련 이력')
        self.button('history_panel', history_label,
                    (analytics_panel is not None and analytics_panel.pending)
                    or state.busy or state.closing)
        self._draw_command_status(state)
        self._draw_api_panel(state, analytics_panel, history_panel)
        self._draw_analytics_panel(analytics_panel)
        self._draw_history_panel(history_panel)

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

    def draw(self, state, analytics_panel=None, history_panel=None):
        self.screen.fill(BG)
        if state.authenticated:
            self._draw_game(state, analytics_panel, history_panel)
        else:
            self._draw_login(state)
        pygame.display.flip()
