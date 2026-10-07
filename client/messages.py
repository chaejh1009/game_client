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
    slot_id: str = 'village-board'
    request_id: int = 0
    decision_id: str = ''
    event_type: str = ''


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
    slot_id: str = 'village-board'
    request_id: int = 0
    decision_id: str = ''
    ad: dict | None = None
    image_bytes: bytes = field(default=b'', repr=False)
    event_type: str = ''
    ad_event: dict | None = None
    event_rejected: bool = False
