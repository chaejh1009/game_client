# `client/state.py`

## 책임과 경계

설정을 검증하고 메인 스레드 게임 상태 전이와 `player_id`별 버전 병합을 수행한다. `StatePort`의 구체 구현이며 네트워크 호출과 pygame 호출은 하지 않는다.

## 호환 이름

- `Request`, `Result`, `PLAYER_FIELDS`, `DELIVERY_FIELDS`: 기존 import 호환을 위해 `messages.py`에서 다시 노출한다. 실제 소유 문서는 [`messages.py.md`](messages.py.md)이다.

## `Config`

불변 dataclass이자 `ConfigPort`의 구조적 구현이다. 값은 `client/config.json`에서 오며 자세한 키는 [`config.json.md`](config.json.md)를 따른다.

필드:

- `server_base_url: str`: 경로 없는 HTTP(S) origin.
- `window_width`, `window_height`, `tile_size: int`: 검증된 화면/타일 크기.
- `assets_dir: Path`: client 내부 자산 디렉터리.
- `grass_path`, `path_path`, `tree_path`, `house_path`, `hero_path: Path`: client 내부 이미지 경로.
- `font_path: Path | None`: 선택 글꼴 경로.

### `Config.load() -> Config` (`@classmethod`)

```text
client/config.json을 UTF-8 JSON 객체로 읽기
server_base_url 기본값과 끝 slash 정리
urlsplit로 scheme/host/credential/path/query/fragment 검증
window_width/window_height/tile_size 정수 및 범위 검증
내부 configured_path로 각 자산 경로 검증
검증·정규화한 값으로 Config 반환
```

외부 호출: `pathlib.Path`, `json.loads`에 해당하는 `Path.read_text` + `json.loads`, `urllib.parse.urlsplit`.

### 내부 `configured_path(key: str, *, optional: bool = False) -> Path | None`

`Config.load`의 지역 함수이며 바깥에서는 호출하지 않는다.

```text
data[key] 조회
optional=True이고 값이 null이면 None
비어 있지 않은 문자열인지 검사
config 파일의 부모인 client 디렉터리를 기준으로 resolve
resolve 결과가 client 디렉터리 밖이면 거부
Path 반환
```

## `State`

`ports.StatePort`를 구조적으로 구현한다. 포트에 없는 player, WS, API, 렌더링용 필드는 구체 상태 내부 데이터이며 상위 유스케이스 계약을 확장하지 않는다.

### 필드와 출처

- 로그인 입력: `username`, `password`, `focus`; pygame 입력에서 온다.
- 수명주기: `authenticated`, `busy`, `closing`, `message`; `controller.py`와 `apply`가 갱신한다.
- player 상태: `player`, `players`, `my_player_id`, `room_id`, `online_count`; 검증된 worker `Result`에서 온다.
- WS 표시: `ws_connected`, `ws_json`; snapshot/state/연결 종료 결과에서 온다.
- API 표시: `api_status`, `api_json`, `api_path`; `Result(kind='api')`에서 온다.
- 전달 상태: `delivery_source`, `event_count`, `pending_publish_count`, `delivery_pending`, `delivery_status`, `last_delivery_at`.
- 명령 상태: `command_pending`, `selected_action`, `selected_direction`, `command_status`, `last_command_at`.

### `State.__post_init__(self) -> None`

```text
초기 player가 있으면:
    my_player_id/room_id 설정
    players[player_id]에 저장
    online_count 계산
```

### `State._merge_player(self, player: dict) -> dict`

```text
player_id로 기존 상태 조회
새 version이 기존 version보다 작으면 기존 상태 반환
그 외 players[player_id] 갱신
자기 player_id이면 self.player도 갱신
online_count 재계산
최종 player 반환
```

동일 version은 수신한 값을 허용하고, 낮은 version만 거부한다.

### `State.begin_command(self, action: str, now: float, direction: str = '') -> bool`

```text
move 방향과 action 허용 목록 검증
인증/종료/busy/기존 명령 진행 여부 검증
train이면 WS 연결과 위치 (3, 2) 검증
마지막 명령 후 0.2초가 지나지 않았으면 거부
last_command_at, pending, 선택 action/direction, status='pending' 설정
action별 안내 메시지 설정
True 반환; 거부 시 False
```

`now`는 `controller.py`가 전달하는 `time.monotonic()` 값이다.

### `State.begin_delivery(self, now: float) -> bool`

```text
인증/종료/기존 delivery 진행 여부 검증
마지막 요청 후 5초 cooldown 검사
last_delivery_at, pending, status='pending', 안내 메시지 설정
True 반환; 거부 시 False
```

### `State.clear_account(self) -> None`

```text
인증과 username/password 제거
player/API/WS/방/온라인 상태 제거
delivery 상태와 cooldown 초기화
command 상태와 rate-limit 시각 초기화
```

### `State.apply(self, result: Result) -> None`

```text
closing이면 무시
api 결과면 API 표시 필드만 갱신하고 반환
ws_json이 있으면 최근 안전 WS JSON 갱신

snapshot이면:
    player_id별로 기존 version이 더 높을 때만 기존 값 보존
    players 전체를 snapshot 범위로 교체
    자기 player/room/online_count/WS 연결 상태 갱신
state이면 _merge_player 후 WS 연결 표시
ws_event이면 표시 JSON 외 상태 병합 없이 반환
ws_disconnected이면 연결 표시와 메시지 갱신

command/command_error이면 command pending 해제와 결과 상태 갱신
delivery/delivery_error이면 delivery pending 해제와 결과 상태 갱신
그 외 결과면 busy 해제
공통 메시지 갱신

player -> 인증, 자기 ID/방/player 병합, WS 상태 갱신
command -> _merge_player
delivery -> 검증된 전달 카운트 저장
logged_out 또는 needs_login -> clear_account
fatal -> clear_account 후 closing=True
```

직접 외부 호출은 `_merge_player`, `clear_account`뿐이며 I/O는 없다.
