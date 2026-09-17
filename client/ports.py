"""Abstract contracts used at client layer boundaries."""
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from messages import Request, Result


class ConfigPort(Protocol):
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


class StatePort(Protocol):
    username: str
    password: str
    focus: str
    authenticated: bool
    busy: bool
    closing: bool
    message: str
    delivery_pending: bool
    delivery_status: str
    delivery_source: str
    event_count: int | None
    pending_publish_count: int | None
    last_delivery_at: float
    command_pending: bool
    command_status: str
    selected_action: str
    selected_direction: str
    player: dict | None
    players: dict
    my_player_id: int | str | None
    room_id: int | str | None
    online_count: int
    ws_connected: bool
    ws_json: dict | None
    api_status: int | None
    api_json: dict | None
    api_path: str

    def begin_command(self, action: str, now: float, direction: str = '') -> bool: ...

    def begin_delivery(self, now: float) -> bool: ...

    def apply(self, result: Result) -> None: ...


class AnalyticsPanelPort(Protocol):
    visible: bool
    pending: bool
    available: bool | None
    schema_version: int | None
    generated_at: str
    event_count: int | None
    by_action: tuple
    by_room: tuple
    message: str

    def begin(self, authenticated: bool, closing: bool) -> bool: ...

    def hide(self) -> None: ...

    def clear(self) -> None: ...

    def apply(self, result: Result) -> bool: ...


class HistoryPanelPort(Protocol):
    visible: bool
    pending: bool
    scope: str
    limit: int | None
    events: tuple
    message: str

    def begin(self) -> bool: ...

    def wait_for_train(self) -> None: ...

    def show(self) -> None: ...

    def hide(self) -> None: ...

    def clear(self) -> None: ...

    def apply(self, result: Result) -> bool: ...


class NetworkPort(Protocol):
    def start(self) -> None: ...

    def submit(self, request: Request) -> None: ...

    def stop(self) -> None: ...

    def get_result_nowait(self) -> Result: ...

    def is_alive(self) -> bool: ...

    def join(self) -> None: ...


class ResponseValidatorPort(Protocol):
    def decode_ws_message(self, message: Any, close_code: int | None) -> dict: ...

    def validate_snapshot(self, data: dict) -> tuple[dict, ...]: ...

    def safe_state_message(self, player: dict,
                           command_id: str | None = None) -> dict: ...

    def safe_error_message(self, data: dict) -> dict: ...

    def command_failure(self, data: dict) -> Exception: ...

    def validate_player(self, data: dict) -> dict: ...

    def validate_delivery(self, data: dict) -> dict: ...

    def validate_analytics(self, data: dict) -> dict: ...

    def validate_history(self, data: dict) -> dict: ...


class AuthPort(Protocol):
    async def login(self, username: str, password: str) -> None: ...

    async def logout(self) -> None: ...

    def clear(self) -> None: ...


class AuthFactoryPort(Protocol):
    def __call__(self, session: Any, origin: str) -> AuthPort: ...


class ApiClientPort(Protocol):
    async def get_player(self) -> dict: ...

    async def get_delivery(self) -> dict: ...

    async def get_analytics(self) -> dict: ...

    async def get_history(self) -> dict: ...


class ApiClientFactoryPort(Protocol):
    def __call__(self, session: Any, origin: str,
                 validator: ResponseValidatorPort,
                 result_sink: Callable[[Result], None]) -> ApiClientPort: ...


class GameSocketPort(Protocol):
    async def connect(self, expected_player_id: int | str) -> tuple[dict, dict]: ...

    def start_listener(self) -> None: ...

    async def command(self, action: str, direction: str) -> dict: ...

    async def close(self) -> None: ...

    async def shutdown(self) -> None: ...


class GameSocketFactoryPort(Protocol):
    def __call__(self, session: Any, origin: str,
                 validator: ResponseValidatorPort,
                 result_sink: Callable[[Result], None]) -> GameSocketPort: ...


class HitTargetPort(Protocol):
    def collidepoint(self, point: Any) -> bool: ...


class RendererPort(Protocol):
    controls: Mapping[str, HitTargetPort]

    def draw(self, state: StatePort, analytics_panel: AnalyticsPanelPort,
             history_panel: HistoryPanelPort) -> None: ...


class RendererFactoryPort(Protocol):
    def __call__(self, config: ConfigPort) -> RendererPort: ...


class ControllerPort(Protocol):
    def submit(self, kind: str) -> bool: ...

    def request_command(self, action: str, direction: str = '') -> bool: ...

    def request_delivery(self) -> bool: ...

    def toggle_analytics(self) -> None: ...

    def toggle_history(self) -> None: ...

    def request_history(self) -> None: ...

    def begin_shutdown(self) -> bool: ...

    def apply_result(self, result: Result) -> None: ...


class ApplicationPort(Protocol):
    def run(self) -> int: ...
