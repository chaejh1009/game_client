# `client/messages.py`

## 책임과 경계

클라이언트 계층 사이를 통과하는 값 계약을 정의한다. 네트워크 전송, 상태 변경, pygame 호출은 하지 않는다. `controller.py`, `network.py`, `ports.py`가 이 값만 공유하므로 네트워크 계층이 구체 `state.py`에 의존하지 않는다.

## 상수

- `PLAYER_FIELDS = ('player_id', 'room_id', 'x', 'y', 'coins', 'version')`: HTTP/WS player 투영에 허용되는 필드 순서.
- `DELIVERY_FIELDS = ('source', 'event_count', 'pending_publish_count')`: delivery 응답 투영에 허용되는 필드 순서.

## `Request`

worker 입력용 dataclass.

- `kind: str`: 요청 분기 키.
- `username: str`, `password: str`: 로그인에만 사용하며 repr에서 숨긴다. 제출·처리 후 비운다.
- `direction: str`: 이동 방향, 기본 `''`.
- `action: str`: 명령 종류, 기본 `'move'`.

메서드와 I/O는 없다.

## `Result`

worker 출력용 불변 dataclass. 비밀번호, cookie, CSRF token, 원문 임의 응답을 포함하지 않는다.

- `kind`, `message`: 결과 라우팅과 사용자용 메시지.
- `player`: 검증된 player 또는 API 패널용 검증 객체.
- `players`: snapshot의 검증된 player tuple.
- `ws_json`: 표시가 허용된 WS 객체.
- `delivery`: 검증된 delivery 객체.
- `api_path`, `status`: API 검사 패널 메타데이터.
- `needs_login`: 계정 상태를 지워야 하는 오류 여부.
- `direction`, `action`: 완료/실패한 게임 명령 식별.

메서드와 I/O는 없다.

## 호출 관계

```text
controller.py -> Request 생성 -> NetworkPort.submit
network.py -> Request 소비
network.py -> Result 생성 -> NetworkPort.get_result_nowait
client_app.py -> ControllerPort.apply_result(Result)
controller.py -> StatePort/PanelPort.apply(Result)
```

