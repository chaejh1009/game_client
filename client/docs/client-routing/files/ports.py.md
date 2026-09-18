# `client/ports.py`

## 책임과 경계

클라이언트 계층 사이의 추상 호출 계약을 `typing.Protocol`로 정의한다. 구현 객체를 생성하거나 I/O를 수행하지 않는다. 구현체는 Protocol을 직접 상속하지 않고 같은 속성과 signature를 제공하는 구조적 부분형 방식으로 계약을 만족한다.

## `ConfigPort`

```text
server_base_url
window_width/window_height/tile_size
assets_dir
grass_path/path_path/tree_path/house_path/hero_path/font_path
```

구현: `state.Config`. composition root, ClientApp, Renderer factory 사이의 설정 계약이다.

## `StatePort`

상위 계층이 사용할 수 있는 로그인·수명주기·요청 진행 필드와 상태 전이만 공개한다.

```text
username/password/focus
authenticated/busy/closing/message
player/players/my_player_id/room_id/online_count
ws_connected/ws_json
api_status/api_json/api_path
delivery 관련 표시·진행 필드
command 관련 표시·진행 필드
begin_command(action, now, direction='') -> bool
begin_delivery(now) -> bool
apply(result: Result) -> None
```

구현: `state.State`.

## `AnalyticsPanelPort`

```text
visible/pending/available/schema_version/generated_at/event_count
by_action/by_room/message
begin(authenticated, closing) -> bool
hide() -> None
clear() -> None
apply(result: Result) -> bool
```

구현: `panels.AnalyticsPanelState`.

## `HistoryPanelPort`

```text
visible/pending/scope/limit/events/message
begin() -> bool
wait_for_train() -> None
show() -> None
hide() -> None
clear() -> None
apply(result: Result) -> bool
```

구현: `panels.HistoryPanelState`.

## `NetworkPort`

worker 내부 Queue와 Thread를 노출하지 않는 애플리케이션용 네트워크 계약이다.

```text
start() -> None
submit(request: Request) -> None
stop() -> None
get_result_nowait() -> Result
is_alive() -> bool
join() -> None
```

구현: `network.NetworkWorker`.

## `ResponseValidatorPort`

```text
decode_ws_message(message, close_code) -> dict
validate_snapshot(data) -> tuple[dict, ...]
safe_state_message(player, command_id=None) -> dict
safe_error_message(data) -> dict
command_failure(data) -> Exception
validate_player(data) -> dict
validate_delivery(data) -> dict
validate_analytics(data) -> dict
validate_history(data) -> dict
```

구현: `network_validation.ResponseValidator`.

## `AuthPort` / `AuthFactoryPort`

```text
AuthFactoryPort(session, origin) -> AuthPort
AuthPort.login(username, password) -> await None
AuthPort.logout() -> await None
AuthPort.clear() -> None
```

구현: `network_auth.DjangoAuth`와 그 class factory.

## `ApiClientPort` / `ApiClientFactoryPort`

```text
ApiClientFactoryPort(session, origin, validator, result_sink) -> ApiClientPort
ApiClientPort.get_player() -> await dict
ApiClientPort.get_delivery() -> await dict
ApiClientPort.get_analytics() -> await dict
ApiClientPort.get_history() -> await dict
```

구현: `network_api.ApiClient`와 그 class factory.

## `GameSocketPort` / `GameSocketFactoryPort`

```text
GameSocketFactoryPort(session, origin, validator, result_sink) -> GameSocketPort
GameSocketPort.connect(expected_player_id) -> await (player, safe_ws_json)
GameSocketPort.start_listener() -> None
GameSocketPort.command(action, direction) -> await player
GameSocketPort.close() -> await None
GameSocketPort.shutdown() -> await None
```

구현: `network_ws.GameSocketClient`와 그 class factory.

## `HitTargetPort`

```text
collidepoint(point) -> bool
```

pygame 타입을 추상계약에 노출하지 않고 clickable control에 필요한 연산만 공개한다.

## `RendererPort`

```text
controls: Mapping[str, HitTargetPort]
draw(state: StatePort,
     analytics_panel: AnalyticsPanelPort,
     history_panel: HistoryPanelPort) -> None
```

구현: `render.Renderer`. 세부 출력은 façade 내부에서 책임별 렌더 모듈로 위임하지만 애플리케이션에 공개되는 계약은 이 포트 하나이다.

## `RendererFactoryPort`

```text
__call__(config: ConfigPort) -> RendererPort
```

`ClientApp`이 pygame 초기화 후 renderer를 만들 수 있게 하면서 concrete `Renderer` import를 피한다. 구현은 composition root가 전달하는 `render.Renderer` class이다.

## `ControllerPort`

```text
submit(kind) -> bool
request_command(action, direction='') -> bool
request_delivery() -> bool
toggle_analytics() -> None
toggle_history() -> None
request_history() -> None
begin_shutdown() -> bool
apply_result(result: Result) -> None
```

구현: `controller.ClientController`.

## `ApplicationPort`

```text
run() -> int
```

구현: `client_app.ClientApp`. `main.py`가 프로세스 실행을 이 계약으로 호출한다.

## 의존 방향

```text
상위 계층 -> ports.py <- 하위 구현
상위 계층 -> messages.py <- 하위 구현

상위 계층 -X-> 하위 concrete 모듈
ports.py   -X-> pygame/network/state/render 구현
```
