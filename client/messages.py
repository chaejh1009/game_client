"""Secret-free request and result values shared across client boundaries."""
from dataclasses import dataclass, field


PLAYER_FIELDS = ('player_id', 'room_id', 'x', 'y', 'coins', 'version')
DELIVERY_FIELDS = ('source', 'event_count', 'pending_publish_count')


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
    ws_json: dict | None = None
    delivery: dict | None = None
    api_path: str = ''
    status: int | None = None
    needs_login: bool = False
    direction: str = ''
    action: str = ''
