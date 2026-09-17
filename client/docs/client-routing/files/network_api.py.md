# `client/network_api.py`

## 책임과 경계

주입받은 단일 ClientSession으로 네 개의 JSON 조회 API를 호출한다. JSON transport 제한은 직접 적용하고 endpoint별 데이터 검증은 `ResponseValidatorPort`로 위임한다. `ApiClientPort`를 구조적으로 구현하며 인증 form, WS, worker task는 알지 않는다.

## `ApiClient` 필드

- `_session`: `network.py`가 만든 단일 ClientSession.
- `_origin`: 검증된 server origin.
- `_validator`: `ResponseValidatorPort`.
- `_result_sink`: 안전한 API inspector `Result`를 worker 결과 큐에 넣는 callback.

## 메서드

### `ApiClient.__init__(self, session: aiohttp.ClientSession, origin: str, validator: ResponseValidatorPort, result_sink: Callable[[Result], None]) -> None`

```text
주입받은 session/origin/validator/result sink 저장
새 session이나 queue를 만들지 않음
```

### `_get(self, path: str, validate: Callable[[dict], dict]) -> dict` (`async`)

```text
status=None, safe=None
GET origin+path, Accept JSON, redirect 비허용
302/401 -> needs_login Failure
403/비-2xx/비-JSON -> Failure
body를 8192-byte chunk로 읽고 65536 bytes 초과 거부
JSON 객체로 decode
safe = validate(data)
safe 반환
finally:
    Result('api', status, safe, path)를 result sink로 전달
```

오류가 나도 status와 검증 성공 전까지의 안전한 값만 API inspector에 전달한다.

### `get_player(self) -> dict` (`async`)

```text
_get('/api/player/', validator.validate_player)
```

### `get_delivery(self) -> dict` (`async`)

```text
_get('/api/delivery/', validator.validate_delivery)
```

### `get_analytics(self) -> dict` (`async`)

```text
_get('/api/analytics/', validator.validate_analytics)
```

### `get_history(self) -> dict` (`async`)

```text
_get('/api/history/', validator.validate_history)
```

