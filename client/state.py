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
        return cls(origin, *sizes, (path.parent / data.get('assets_dir', 'assets')).resolve())

@dataclass
class Request:
    kind: str
    username: str = field(default='', repr=False)
    password: str = field(default='', repr=False)

@dataclass(frozen=True)
class Result:
    kind: str
    message: str = ''
    player: dict | None = None
    status: int | None = None
    needs_login: bool = False

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
    api_status: int | None = None
    api_json: dict | None = None

    def clear_account(self):
        self.authenticated = False
        self.username = self.password = ''
        self.player = self.api_json = None
        self.api_status = None

    def apply(self, result):
        if self.closing:
            return
        if result.kind == 'api':
            self.api_status, self.api_json = result.status, result.player
            return
        self.busy = False
        self.message = result.message
        if result.kind == 'player':
            self.authenticated = True
            self.player = result.player
        elif result.kind == 'logged_out' or result.needs_login:
            self.clear_account()
        elif result.kind == 'fatal':
            self.clear_account()
            self.closing = True
