# `client/network_validation.py`

## 책임과 경계

외부 HTTP/WS 데이터를 허용 필드로 검증·투영하는 순수 검증 컴포넌트다. `ResponseValidatorPort`를 구조적으로 구현하며 session, socket, queue, pygame을 알지 않는다.

## `ResponseValidator` 메서드

### `decode_ws_message(self, message, close_code: int | None) -> dict`

```text
TEXT가 아니면 close_code 4401 여부를 needs_login으로 Failure
message.data 65536 초과 거부
JSON 객체 decode, 실패/비객체 거부
dict 반환
```

### `validate_snapshot(self, data: dict) -> tuple[dict, ...]`

```text
players가 최대 100개 list인지 검사
각 항목 validate_player
player_id 중복 거부
tuple 반환
```

### `safe_state_message(self, player: dict, command_id: str | None = None) -> dict`

```text
type='state'와 검증된 player 복사
최대 80자 문자열 command_id만 추가
```

### `safe_error_message(self, data: dict) -> dict`

```text
type='error'와 최대 80자 code 구성
최대 80자 문자열 command_id만 추가
```

### `command_failure(self, data: dict) -> Failure`

```text
too_fast/outside_map/invalid_direction/not_at_gather_tile/
not_at_train_tile/unknown_action을 안전한 한국어 메시지로 매핑
알 수 없는 code는 일반 명령 실패 메시지
```

### `validate_player(self, data: dict) -> dict`

```text
객체인지 검사
PLAYER_FIELDS만 순회
player_id/room_id는 int 또는 최대 80자 문자열
나머지는 정확한 int
허용 필드 dict 반환
```

### `validate_delivery(self, data: dict) -> dict`

```text
source가 비어 있지 않은 최대 80자 문자열인지 검사
나머지 DELIVERY_FIELDS가 음이 아닌 정확한 int인지 검사
허용 필드 dict 반환
```

### 내부 `_validate_analytics_rows(self, rows, label_key: str, field_name: str) -> tuple`

```text
최대 100개 list와 각 row 객체 검사
label과 음이 아닌 int count 검사
room_id label만 int도 허용
허용 필드 tuple 반환
```

### `validate_analytics(self, data: dict) -> dict`

```text
available bool 검사
False이면 {'available': False}
True이면 source_topic/source_kind가 비어 있지 않은 제한 길이 문자열인지 검사
raw_record_count가 음이 아닌 정확한 int인지 검사
summary 객체의 generated_at/event_count 검사
summary.by_action은 action_label/count로 검증
summary.by_room은 room_id/count로 검증
안전한 집계 객체 반환
```

추가 최상위 필드, summary 내부 필드, 각 행의 추가 필드는 반환 객체에서 제거한다. 인증 정보나 원문 응답은 보존하지 않는다.

### `validate_ingest(self, data: dict) -> dict`

```text
available bool 검사
False이면 reason 생략은 빈 문자열로 처리하고, 값이 있으면 빈 문자열을 포함한 최대 160자 문자열만 허용
null/숫자/bool/list/object와 160자 초과 문자열은 Failure로 거부
검증을 통과한 미생성 응답은 {'available': False, 'reason': ...} 반환
True이면 source/generated_at 문자열과 record_count/event_count/
duplicate_record_count 음이 아닌 정확한 int 검사
by_action 각 행의 event_type 문자열과 count 정수 검사
허용된 수집 snapshot 필드만 반환
```

available=false 응답의 카운트나 비허용 필드는 반환하지 않으므로 준비 전 상태를 실제 0건으로 표시하지 않는다. `raw_value`, `evidence`, 인증 정보 등 추가 필드는 안전 투영에서 제거한다. `validate_ingest_analytics`는 같은 검증을 호출하는 호환 별칭이다.

### `validate_history(self, data: dict) -> dict`

```text
scope='current-player', limit 1..100, events 길이 검사
각 event의 schema/id/type/player/room/time/payload 검사
payload에서 x/y/coins/version만 정수로 투영
선택 transition의 step>=1, reward 숫자 검사
안전한 scope/limit/events 객체 반환
```
