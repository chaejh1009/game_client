# Client routing

이 문서는 `python client/main.py`로 실행되는 pygame 클라이언트의 탐색 진입점이다.
책임 분리와 행동 통계 패널 작업이 기존 계약을 깨지 않도록 현재 호출 경계를 기록한다.

## 범위

라우팅 대상은 직접 유지보수하는 런타임 소스와 설정 파일이다. 각 대상은 `files/<client 상대경로>.md`와 정확히 하나씩 대응한다.

| 실제 파일 | 라우팅 문서 | 책임 |
|---|---|---|
| `client/main.py` | [`files/main.py.md`](files/main.py.md) | 설정 로드, 객체 조립, 프로세스 진입점 |
| `client/client_app.py` | [`files/client_app.py.md`](files/client_app.py.md) | pygame 수명주기, 이벤트·결과 루프, 60 FPS 유지 |
| `client/controller.py` | [`files/controller.py.md`](files/controller.py.md) | 로그인·명령·조회·패널 유스케이스 조정 |
| `client/ports.py` | [`files/ports.py.md`](files/ports.py.md) | 계층 사이의 추상 호출 계약 |
| `client/messages.py` | [`files/messages.py.md`](files/messages.py.md) | 계층 사이의 요청·결과 값 계약 |
| `client/network.py` | [`files/network.py.md`](files/network.py.md) | worker 수명주기와 네트워크 유스케이스 조정 |
| `client/network_auth.py` | [`files/network_auth.py.md`](files/network_auth.py.md) | Django form/CSRF/cookie 인증 |
| `client/network_api.py` | [`files/network_api.py.md`](files/network_api.py.md) | 검증된 JSON API 조회 |
| `client/network_ws.py` | [`files/network_ws.py.md`](files/network_ws.py.md) | `/ws/play/`, broadcast, `command_id` 대기 |
| `client/network_validation.py` | [`files/network_validation.py.md`](files/network_validation.py.md) | HTTP/WS 응답 검증과 안전 투영 |
| `client/network_errors.py` | [`files/network_errors.py.md`](files/network_errors.py.md) | 네트워크 컴포넌트 공통 안전 오류 |
| `client/panels.py` | [`files/panels.py.md`](files/panels.py.md) | 통계·이력 패널 상태 전이 |
| `client/render.py` | [`files/render.py.md`](files/render.py.md) | `RendererPort` façade와 장면 선택 |
| `client/render_support.py` | [`files/render_support.py.md`](files/render_support.py.md) | pygame 자산·글꼴·배치·공통 출력 |
| `client/render_login.py` | [`files/render_login.py.md`](files/render_login.py.md) | 로그인 장면 출력 |
| `client/render_game.py` | [`files/render_game.py.md`](files/render_game.py.md) | 인증 후 게임 장면 조정 |
| `client/render_world.py` | [`files/render_world.py.md`](files/render_world.py.md) | 마을 맵과 플레이어 출력 |
| `client/render_panels.py` | [`files/render_panels.py.md`](files/render_panels.py.md) | API·통계·이력 패널 출력 |
| `client/state.py` | [`files/state.py.md`](files/state.py.md) | 설정과 게임 UI 상태 |
| `client/config.json` | [`files/config.json.md`](files/config.json.md) | 실행 시 읽는 클라이언트 설정 값 |

`client/assets/**`는 렌더러가 소비하는 정적 바이너리/외부 배포 자산이므로 호출 라우팅 대상에서 제외한다. 실제로 참조되는 자산 경로는 `config.json.md`와 `render.py.md`에 기록한다. `.venv`, `__pycache__`, `.DS_Store` 같은 생성·로컬 파일도 제외한다.

## 계층별 호출 구조

```text
main.py : 구체 구현 생성 및 추상계약 타입으로 조립
  -> ApplicationPort.run()
     -> client_app.py : pygame 초기화, 사용자 이벤트와 worker 결과 소비
        -> ControllerPort -> controller.py
           -> StatePort -> state.py
           -> AnalyticsPanelPort/HistoryPanelPort -> panels.py
           -> NetworkPort -> network.py
        -> NetworkPort -> network.py
        -> RendererFactoryPort -> render.Renderer 생성
        -> RendererPort -> render.py
           -> render_support.py : 자산, 배치, primitive
           -> render_login.py : 로그인 장면
           -> render_game.py : 게임 장면 조정
              -> render_world.py : 맵과 플레이어
              -> render_panels.py : API, 통계, 이력

controller.py / network.py
  -> messages.py : Request/Result 값 계약

network.py
  -> AuthFactoryPort -> AuthPort -> network_auth.py
     -> /accounts/login/, /accounts/logout/
  -> ApiClientFactoryPort -> ApiClientPort -> network_api.py
     -> /api/player/, /api/delivery/, /api/analytics/actions/, /api/history/
  -> GameSocketFactoryPort -> GameSocketPort -> network_ws.py
     -> /ws/play/
  -> ResponseValidatorPort -> network_validation.py
  -> Result 반환
```

각 계층은 다음 경계까지만 안다.

- `main.py`: 유일한 composition root로서 구체 구현을 생성하지만, 실행 호출은 `ApplicationPort` 계약을 따른다.
- `client_app.py`: `ConfigPort`, `ControllerPort`, `NetworkPort`, `RendererFactoryPort`, `RendererPort`, 상태·패널 포트만 알고 구체 구현 모듈은 import하지 않는다.
- `controller.py`: `StatePort`, 두 패널 포트, `NetworkPort`만 호출하며 pygame과 구체 구현은 모른다.
- `ports.py`: 상위 계층이 사용할 수 있는 속성과 메서드만 선언하고 구현과 I/O를 갖지 않는다.
- `messages.py`: `Request`, `Result`와 허용 필드 상수만 정의하며 상태나 I/O를 갖지 않는다.
- `network.py`: 요청 종류와 동시 task 정책만 알고 인증·API·WS·검증 구현은 포트로 호출한다.
- `network_auth.py`: Django form/CSRF/cookie 계약만 안다.
- `network_api.py`: 네 JSON endpoint와 JSON transport 제한만 알고 검증은 `ResponseValidatorPort`에 맡긴다.
- `network_ws.py`: `/ws/play/`, broadcast, `command_id` waiter만 알고 응답 검증은 `ResponseValidatorPort`에 맡긴다.
- `network_validation.py`: 외부 데이터 검증과 안전 투영만 하며 네트워크 I/O를 하지 않는다.
- `network_errors.py`: 사용자에게 노출 가능한 메시지와 로그인 필요 여부만 보존한다.
- `state.py`: 허용된 행동과 결과 병합 규칙은 알지만 큐, HTTP, WS, pygame은 모른다.
- `panels.py`: 패널별 표시 상태와 관련 `Result.kind`만 알며 서버 호출 방식은 모른다.
- `render.py`: `RendererPort` façade로서 장면만 선택하고 frame을 표시한다.
- `render_support.py`: 상태를 모르며 pygame 자산, 배치, hitbox와 공통 출력만 소유한다.
- `render_login.py`, `render_game.py`, `render_world.py`, `render_panels.py`: 각자 맡은 장면을 포트 상태에서 읽어 출력하며 요청을 만들거나 상태를 변경하지 않는다.
- `config.json`: 값만 제공하며 호출 관계를 갖지 않는다.

## 추상계약 규칙

1. `main.py`만 구체 구현 클래스를 import하고 생성할 수 있다.
2. 상위 계층은 하위 구현 객체를 주입받되 `ports.py`의 Protocol 타입으로만 보관·호출한다.
3. `client_app.py`는 renderer, controller, network의 concrete 모듈을 import하지 않는다.
4. `controller.py`는 State, PanelState, NetworkWorker concrete 클래스를 import하지 않는다.
5. 네트워크 요청과 결과는 `messages.py` 값으로만 경계를 통과한다.
6. 구현체는 Protocol을 상속할 필요 없이 같은 signature를 제공하는 구조적 부분형 계약을 따른다.
7. `network.py`는 `network_auth`, `network_api`, `network_ws`, `network_validation` concrete 모듈을 import하지 않는다.

## 반드시 유지할 기준선

- 실행 명령은 `python client/main.py`이다.
- 로그인은 Django form/CSRF/cookie 흐름을 유지한다.
- 게임 소켓은 `/ws/play/`를 사용한다.
- 방 `snapshot`과 개별 `state`를 모두 처리한다.
- 이동, 채집, 수련 명령을 유지한다.
- 자기 명령은 생성한 `command_id`와 일치하는 응답을 기다린 뒤 완료한다.
- 다른 플레이어 broadcast는 자기 명령 완료로 취급하지 않는다.
- 플레이어 병합은 `player_id`별 `version`이 낮은 상태로 되돌아가지 않는다.
- 최근 행동 이력 패널과 `/api/history/` 검사 기능을 유지한다.
- 행동 통계 패널은 사용자가 조회를 요청했을 때 읽은 `/api/analytics/actions/`의 고정 snapshot만 표시한다.
- replay 기능과 replay 호출 경로는 만들지 않는다.
- 서버 코드와 API/WS 계약은 이 문서화 단계의 변경 대상이 아니다.

## 문서 갱신 규칙

1. 런타임 소스나 설정 파일을 추가·이동·삭제하면 동일한 상대경로의 `.md`를 `files/` 아래에 함께 추가·이동·삭제한다.
2. 파일별 문서는 그 파일이 소유한 책임, 값, 함수/메서드, 바로 호출하는 외부 코드까지만 기술한다.
3. 함수 설명은 `signature -> guard/변환 -> 외부 호출 -> 반환/상태 변화` 순서의 의사코드로 적는다.
4. 다른 계층의 내부 구현은 중복 설명하지 않고 대응 문서로 링크한다.
5. 서버 계약이 달라 보이는 경우 클라이언트 문서만 임의로 바꾸지 말고 계약 변경 여부를 먼저 확인한다.
