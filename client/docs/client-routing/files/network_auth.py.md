# `client/network_auth.py`

## 책임과 경계

주입받은 `aiohttp.ClientSession`으로 Django form 로그인·로그아웃과 CSRF/cookie 수명주기를 처리한다. `AuthPort`를 구조적으로 구현한다. JSON API, WebSocket, worker task, UI 상태는 알지 않는다.

## `DjangoAuth` 필드

- `_session`: `network.py`가 만든 단일 ClientSession.
- `_origin`: 검증된 server origin.
- `_token`: Django CSRF token. 메모리에서만 유지한다.

## 메서드

### `DjangoAuth.__init__(self, session: aiohttp.ClientSession, origin: str) -> None`

```text
주입받은 session/origin 저장
CSRF token을 빈 문자열로 초기화
```

### `clear(self) -> None`

```text
주입받은 session의 cookie jar 비우기
CSRF token 제거
```

### `_discard_html(self, response) -> None` (`async`)

```text
response body를 8192-byte chunk로 소비
누적 65536 bytes 초과면 Failure
```

### `_csrf_from_response(self, response) -> None`

```text
response.cookies['csrftoken'] 조회
없거나 512자 초과면 Failure
검증된 token 저장
```

### `_prepare_login(self) -> None` (`async`)

```text
GET /accounts/login/, Accept HTML, redirect 비허용
404/비-2xx 거부
제한된 HTML body 소비
CSRF cookie 저장
```

### `login(self, username: str, password: str) -> None` (`async`)

```text
_prepare_login()
username/password form과 CSRF/Origin/Referer header 구성
POST /accounts/login/, redirect 비허용
403 거부
301/302/303이면 body 소비, 회전된 CSRF 저장, 성공
200이면 body 소비 후 인증 실패 Failure(needs_login=True)
그 외 상태 Failure
finally form dict 비우기
```

### `logout(self) -> None` (`async`)

```text
CSRF token 필수 검사
POST /accounts/logout/에 빈 form과 CSRF/Origin/Referer 전송
200/204/301/302/303 외 상태 거부
제한된 HTML body 소비
```

credential 원문은 `network.py`가 지역 변수로 전달하고 즉시 제거한다.

