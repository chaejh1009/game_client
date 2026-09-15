"""Main-thread UI state and deliberately secret-free worker results."""
from dataclasses import dataclass, field
from pathlib import Path
import json
from urllib.parse import urlsplit

PLAYER_FIELDS = ('player_id', 'room_id', 'x', 'y', 'coins', 'version')

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
class Request:
    kind: str
    username: str = field(default='', repr=False)
    password: str = field(default='', repr=False)
    direction: str = ''
    action: str = 'move'

@dataclass(frozen=True)
class Result:
    kind: str
    message: str = ''
    player: dict | None = None
    players: tuple = ()
    status: int | None = None
    needs_login: bool = False
    direction: str = ''
    action: str = ''

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
    api_status: int | None = None
    api_json: dict | None = None
    command_pending: bool = False
    selected_action: str = ''
    selected_direction: str = ''
    command_status: str = ''
    last_command_at: float = -1.0

    def begin_command(self, action, now, direction=''):
        if action == 'move' and direction not in ('up', 'down', 'left', 'right'):
            return False
        if action not in ('move', 'gather'):
            return False
        if not self.authenticated:
            self.message = '로그인 입력 중에는 게임 명령을 사용할 수 없습니다.'
            return False
        if self.closing or self.busy or self.command_pending:
            return False
        if self.last_command_at >= 0 and now - self.last_command_at < 0.2:
            self.message = '이동과 채굴 명령은 모두 합쳐 초당 최대 5개입니다.'
            return False
        self.last_command_at = now
        self.command_pending = True
        self.selected_action = action
        self.selected_direction = direction
        self.command_status = 'pending'
        self.message = '코인 채굴 중…' if action == 'gather' else '이동 명령 처리 중…'
        return True

    def clear_account(self):
        self.authenticated = False
        self.username = self.password = ''
        self.player = self.api_json = None
        self.players.clear()
        self.api_status = None
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
            return
        if result.kind == 'snapshot':
            self.players = {player['player_id']: player for player in result.players}
            if self.player is not None:
                current = self.players.get(self.player['player_id'])
                if current is not None:
                    self.player = current
                else:
                    self.players[self.player['player_id']] = self.player
            return
        if result.kind == 'state':
            self.players[result.player['player_id']] = result.player
            if self.player is not None and result.player['player_id'] == self.player['player_id']:
                self.player = result.player
            return
        if result.kind in ('command', 'command_error'):
            self.command_pending = False
            self.command_status = 'success' if result.kind == 'command' else 'error'
            self.selected_action = result.action
            self.selected_direction = result.direction
        else:
            self.busy = False
        self.message = result.message
        if result.kind == 'player':
            self.authenticated = True
            self.player = result.player
            self.players[result.player['player_id']] = result.player
        elif result.kind == 'command':
            self.player = result.player
            self.players[result.player['player_id']] = result.player
        elif result.kind == 'logged_out' or result.needs_login:
            self.clear_account()
        elif result.kind == 'fatal':
            self.clear_account()
            self.closing = True
