# `client/main.py`

## 책임과 경계

프로세스 진입점이자 composition root이다. 설정을 읽고 애플리케이션 구성 객체를 생성·연결한 뒤 `ClientApp.run()`을 호출한다. pygame 수명주기, 이벤트 처리, 유스케이스 규칙, HTTP/WS 형식, 렌더링 세부 구현은 알지 않는다.

직접 호출하는 클라이언트 코드:

- `state.Config.load`, `state.State`
- `panels.AnalyticsPanelState`, `panels.HistoryPanelState`
- `network.NetworkWorker`
- `network_auth.DjangoAuth`
- `network_api.ApiClient`
- `network_ws.GameSocketClient`
- `network_validation.ResponseValidator`
- `controller.ClientController`
- `client_app.ClientApp`
- `render.Renderer`
- `ports`의 애플리케이션·상태·패널·네트워크·controller·renderer factory 계약

## 함수

### `main() -> int`

```text
Config.load()로 client/config.json 검증 및 로드 후 ConfigPort로 보관
실패하면 설정 안내를 출력하고 1 반환

State 생성 후 StatePort로 보관
AnalyticsPanelState, HistoryPanelState 생성 후 각 panel port로 보관
각 네트워크 component class를 factory port로 보관
ResponseValidator를 ResponseValidatorPort로 보관
NetworkWorker(origin, 세 factory, validator) 생성 후 NetworkPort로 보관
ClientController(state, 두 panel state, worker) 생성 후 ControllerPort로 보관
Renderer concrete class를 RendererFactoryPort로 보관
ClientApp(..., renderer_factory) 생성 후 ApplicationPort로 보관
ApplicationPort.run() 결과 반환
```

pygame은 이 파일에서 import하지 않는다. 구체 구현은 이 composition root에서만 선택하며 런타임 호출은 포트 변수의 메서드를 사용한다.

## 지역 변수와 출처

- `config`: `Config.load()` 결과.
- `state`: 메인 스레드 게임 상태.
- `analytics_panel`, `history_panel`: 선택 패널 상태.
- `worker`: 유일한 네트워크 worker.
- `auth_factory`, `api_factory`, `game_socket_factory`: worker event loop 안에서 하위 컴포넌트를 만드는 추상 factory.
- `validator`: HTTP/WS 데이터 검증 계약.
- `controller`: 상태와 worker 사이의 유스케이스 조정자.
- `renderer_factory`: pygame 초기화 후 Renderer를 만들 추상 factory 계약.
- `app`: pygame 수명주기와 메인 루프 소유자.

## 실행

```text
python client/main.py
  -> main()
  -> ClientApp.run()
  -> 종료 코드로 SystemExit
```
