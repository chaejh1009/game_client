"""Configuration and main-thread UI state."""
from dataclasses import dataclass, field
from pathlib import Path
import json
from urllib.parse import urlsplit

from messages import DELIVERY_FIELDS, PLAYER_FIELDS, Request, Result

@dataclass(frozen=True)
class Config:
    server_base_url: str
    window_width: int
    window_height: int
    tile_size: int
    assets_dir: Path
    grass_path: Path
    path_path: Path
    tree_path: Path
    house_path: Path
    hero_path: Path
    font_path: Path | None

    @classmethod
    def load(cls):
        path = Path(__file__).resolve().parent / 'config.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        origin = data.get('server_base_url', 'http://127.0.0.1:8000').rstrip('/')
        url = urlsplit(origin)
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username
                or url.password or url.path or url.query or url.fragment):
            raise ValueError('server_base_url에는 경로 없는 HTTP origin을 지정하세요.')
        sizes = [data.get('window_width', 960), data.get('window_height', 720),
                 data.get('tile_size', 32)]
        if any(type(v) is not int for v in sizes) or not (
                640 <= sizes[0] <= 3840 and 600 <= sizes[1] <= 2160 and 8 <= sizes[2] <= 128):
            raise ValueError('창 크기는 640×600~3840×2160, 타일은 8~128 정수여야 합니다.')
        def configured_path(key, *, optional=False):
            value = data.get(key)
            if optional and value is None:
                return None
            if not isinstance(value, str) or not value:
                raise ValueError(f'client/config.json의 {key} 경로를 확인하세요.')
            resolved = (path.parent / value).resolve()
            if not resolved.is_relative_to(path.parent):
                raise ValueError(f'{key}는 client 폴더 안의 경로여야 합니다.')
            return resolved

        return cls(
            server_base_url=origin,
            window_width=sizes[0],
            window_height=sizes[1],
            tile_size=sizes[2],
            assets_dir=(path.parent / data.get('assets_dir', 'assets')).resolve(),
            grass_path=configured_path('grass_path'),
            path_path=configured_path('path_path'),
            tree_path=configured_path('tree_path'),
            house_path=configured_path('house_path'),
            hero_path=configured_path('hero_path'),
            font_path=configured_path('font_path', optional=True),
        )

@dataclass
class State:
    username: str = ''
    password: str = field(default='', repr=False)
    focus: str = 'username'
    authenticated: bool = False
    busy: bool = False
    closing: bool = False
    message: str = '교실 서버 계정으로 접속하세요.'
    player: dict | None = None
    players: dict = field(default_factory=dict)
    my_player_id: int | str | None = None
    room_id: int | str | None = None
    online_count: int = 0
    ws_connected: bool = False
    ws_json: dict | None = None
    api_status: int | None = None
    api_json: dict | None = None
    api_path: str = ''
    delivery_source: str = ''
    event_count: int | None = None
    pending_publish_count: int | None = None
    delivery_pending: bool = False
    delivery_status: str = ''
    last_delivery_at: float = -1.0
    command_pending: bool = False
    selected_action: str = ''
    selected_direction: str = ''
    command_status: str = ''
    last_command_at: float = -1.0

    def __post_init__(self):
        if self.player is not None:
            self.my_player_id = self.player['player_id']
            self.room_id = self.player['room_id']
            self.players[self.my_player_id] = self.player
            self.online_count = len(self.players)

    def _merge_player(self, player):
        player_id = player['player_id']
        previous = self.players.get(player_id)
        if previous is not None and player['version'] < previous['version']:
            return previous
        self.players[player_id] = player
        if player_id == self.my_player_id:
            self.player = player
        self.online_count = len(self.players)
        return player

    def begin_command(self, action, now, direction=''):
        if action == 'move' and direction not in ('up', 'down', 'left', 'right'):
            return False
        if action not in ('move', 'gather', 'train'):
            return False
        if not self.authenticated:
            self.message = '로그인 입력 중에는 게임 명령을 사용할 수 없습니다.'
            return False
        if self.closing or self.busy or self.command_pending:
            return False
        if action == 'train':
            if not self.ws_connected:
                self.message = '게임 연결이 열려 있을 때만 수련할 수 있습니다.'
                return False
            if self.player is None or (self.player['x'], self.player['y']) != (3, 2):
                self.message = '개인 수련은 수련 타일 (3, 2)에서만 가능합니다.'
                return False
        if self.last_command_at >= 0 and now - self.last_command_at < 0.2:
            self.message = '게임 명령은 모두 합쳐 초당 최대 5개입니다.'
            return False
        self.last_command_at = now
        self.command_pending = True
        self.selected_action = action
        self.selected_direction = direction
        self.command_status = 'pending'
        messages = {
            'gather': '코인 채굴 중…',
            'train': '개인 수련 명령 처리 중…',
            'move': '이동 명령 처리 중…',
        }
        self.message = messages[action]
        return True

    def begin_delivery(self, now):
        if not self.authenticated or self.closing or self.delivery_pending:
            return False
        if self.last_delivery_at >= 0 and now - self.last_delivery_at < 5.0:
            remaining = max(1, int(5.0 - (now - self.last_delivery_at) + 0.999))
            self.message = f'이벤트 전달 상태는 {remaining}초 뒤 다시 확인할 수 있습니다.'
            return False
        self.last_delivery_at = now
        self.delivery_pending = True
        self.delivery_status = 'pending'
        self.message = '내 이벤트 전달 상태를 확인하는 중…'
        return True

    def clear_account(self):
        self.authenticated = False
        self.username = self.password = ''
        self.player = self.api_json = None
        self.players.clear()
        self.my_player_id = self.room_id = None
        self.online_count = 0
        self.ws_connected = False
        self.ws_json = None
        self.api_status = None
        self.api_path = ''
        self.delivery_source = ''
        self.event_count = self.pending_publish_count = None
        self.delivery_pending = False
        self.delivery_status = ''
        self.last_delivery_at = -1.0
        self.command_pending = False
        self.selected_action = ''
        self.selected_direction = ''
        self.command_status = ''
        self.last_command_at = -1.0

    def apply(self, result):
        if self.closing:
            return
        if result.kind == 'api':
            self.api_status, self.api_json = result.status, result.player
            self.api_path = result.api_path
            return
        if result.ws_json is not None:
            self.ws_json = result.ws_json
        if result.kind == 'snapshot':
            merged = {}
            for player in result.players:
                previous = self.players.get(player['player_id'])
                merged[player['player_id']] = (previous if previous is not None
                                                and previous['version'] > player['version']
                                                else player)
            self.players = merged
            own = self.players.get(self.my_player_id)
            if own is not None:
                self.player = own
                self.room_id = own['room_id']
            elif result.players:
                self.room_id = result.players[0]['room_id']
            self.online_count = len(self.players)
            self.ws_connected = True
            return
        if result.kind == 'state':
            self._merge_player(result.player)
            self.ws_connected = True
            return
        if result.kind == 'ws_event':
            return
        if result.kind == 'ws_disconnected':
            self.ws_connected = False
            self.message = result.message
            return
        if result.kind in ('command', 'command_error'):
            self.command_pending = False
            self.command_status = 'success' if result.kind == 'command' else 'error'
            self.selected_action = result.action
            self.selected_direction = result.direction
        elif result.kind in ('delivery', 'delivery_error'):
            self.delivery_pending = False
            self.delivery_status = 'success' if result.kind == 'delivery' else 'error'
        else:
            self.busy = False
        self.message = result.message
        if result.kind == 'player':
            self.authenticated = True
            if self.my_player_id is None:
                self.my_player_id = result.player['player_id']
            if result.player['player_id'] == self.my_player_id:
                self.room_id = result.player['room_id']
                self._merge_player(result.player)
            if result.ws_json is not None:
                self.ws_connected = True
        elif result.kind == 'command':
            self._merge_player(result.player)
        elif result.kind == 'delivery':
            self.delivery_source = result.delivery['source']
            self.event_count = result.delivery['event_count']
            self.pending_publish_count = result.delivery['pending_publish_count']
        elif result.kind == 'logged_out' or result.needs_login:
            self.clear_account()
        elif result.kind == 'fatal':
            self.clear_account()
            self.closing = True
