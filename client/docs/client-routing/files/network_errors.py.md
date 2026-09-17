# `client/network_errors.py`

## 책임과 경계

분리된 네트워크 컴포넌트가 공유하는 안전한 예외 값만 정의한다. I/O, 상태 변경, pygame 호출은 없다.

## `Failure`

### `Failure.__init__(self, message: str, needs_login: bool = False) -> None`

파라미터:

- `message`: 사용자에게 표시할 수 있는 정제된 오류 문자열.
- `needs_login`: socket과 인증 상태를 정리해야 하는지 나타내는 값.

```text
Exception(message) 초기화
self.needs_login 저장
```

HTTP body, header, cookie, token, traceback 같은 원문 비밀정보를 보관하지 않는다.

