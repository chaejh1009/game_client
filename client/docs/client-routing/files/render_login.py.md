# `client/render_login.py`

## 책임과 경계

로그인 장면만 출력한다. `StatePort`에서 사용자명, 비밀번호 길이, focus, busy/closing, 안내 메시지를 읽고 `RenderSupport`의 primitive를 호출한다.

## `draw_login(view: RenderSupport, state: StatePort) -> None`

```text
제목과 server origin 출력
username/password 입력 영역과 focus 테두리 출력
password는 길이만큼 `*`로 표시
login 버튼과 키 안내 출력
자산 오류가 있으면 오류색 안내 출력
```

입력 처리와 로그인 요청은 수행하지 않으며 상태를 변경하지 않는다.
