# `client/network_ws.py`

## 책임과 경계

`/ws/play/` 연결, 첫 player 확인, broadcast 소비, 게임 명령 전송과 `command_id` 일치 대기를 소유한다. `GameSocketPort`를 구조적으로 구현한다. 응답 데이터 검증과 안전 투영은 `ResponseValidatorPort`로 호출하고, 결과는 주입받은 sink로 전달한다.

## `GameSocketClient` 필드

- `_session`, `_origin`: worker가 주입한 단일 session과 origin.
- `_validator`: `ResponseValidatorPort`.
- `_result_sink`: 검증된 `Result` callback.
- `_ws`, `_reader`: socket과 reader task.
- `_command_waiter`, `_command_id`: 현재 자기 명령의 Future와 UUID.
- `_player_id`: 로그인한 자기 player 식별자.
- `_last_command_at`: 모든 게임 명령 합계 0.2초 제한 기준.

## 메서드

### `GameSocketClient.__init__(self, session, origin: str, validator: ResponseValidatorPort, result_sink) -> None`

```text
주입값 저장
socket/reader/waiter/player/rate-limit 상태 초기화
```

### `close(self) -> None` (`async`)

```text
현재 task가 아닌 reader 취소 및 회수
socket이 있으면 최대 1초 안에 close
socket과 player_id 제거
```

### `shutdown(self) -> None` (`async`)

```text
close()
명령 rate-limit 시각 초기화
```

### `_receive_initial_state(self) -> tuple[dict, dict]` (`async`)

```text
최대 2초 동안 첫 WS 메시지 수신
validator.decode_ws_message
error type이면 validator.command_failure를 raise
validator.validate_player
(player, validator.safe_state_message(...)) 반환
```

### `connect(self, expected_player_id: int | str) -> tuple[dict, dict]` (`async`)

```text
origin을 ws/wss로 바꾸고 경로를 /ws/play/로 고정
origin header와 max_msg_size=65536으로 연결
_receive_initial_state()
HTTP에서 받은 expected_player_id와 WS player_id 일치 검사
자기 player_id 저장
(player, safe WS JSON) 반환
```

### `start_listener(self) -> None`

```text
현재 event loop에 _listen task 생성
```

### `_listen(self) -> None` (`async`)

```text
WS 메시지 순회, validator.decode_ws_message
snapshot -> validate_snapshot 후 Result('snapshot')
error -> safe_error_message로 Result('ws_event')
         현재 command_id와 같으면 waiter에 command Failure
state -> validate_player와 safe_state_message

다른 player_id면 Result('state')
자기 player이고 command waiter가 pending이면:
    Result('ws_event')로 inspector만 갱신
    command_id가 같을 때만 waiter 완료
waiter가 없으면 Result('state')

알려진 연결/검증 오류는 waiter 또는 Result('error')로 전달
finally 남은 waiter 실패 처리, 자연 종료면 ws_disconnected 전달
```

### `command(self, action: str, direction: str) -> dict` (`async`)

```text
열린 socket인지 검사
action이 move/gather/train인지 검사
monotonic 기준 0.2초 rate limit 검사
UUID command_id와 payload 생성
move이면 direction 추가
현재 command waiter 생성
send_json(payload)
최대 2초 동안 _listen이 같은 command_id로 완료할 Future 대기
검증된 자기 player 반환
finally waiter와 command_id 제거
```

다른 player broadcast나 불일치 `command_id`는 자기 명령을 완료하지 않는다. replay 메시지는 처리하지 않는다.

