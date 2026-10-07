# `client/client_app.py`

## 하단 카드 이벤트

인증 상태의 `_control_names`에 `load_refresh`, `metrics_refresh`를 포함한다. `_handle_mouse`는 화면 좌표를 콘텐츠 좌표로 변환한 뒤 해당 버튼을 `ControllerPort.request_measurement`로 라우팅한다. `_handle_event`는 `VIDEORESIZE`와 `MOUSEWHEEL`을 렌더러의 크기 변경·스크롤 메서드로 전달한다. 결과는 기존 `_drain_results` queue 경로로 소비한다.

## 책임과 경계

pygame 초기화·종료와 메인 스레드 프레임 루프를 소유한다. 사용자 이벤트를 `ControllerPort`로 라우팅하고 `NetworkPort` 결과를 소비하며 `RendererPort`를 매 프레임 호출한다. 요청 허용 규칙, 상태 병합, 서버 프로토콜과 구체 구현은 알지 않는다.

직접 호출하는 클라이언트 코드:

- `ports.ControllerPort`
- `ports.NetworkPort`
- `ports.RendererFactoryPort`, `ports.RendererPort`
- `ports.StatePort`, `ports.AnalyticsPanelPort`, `ports.HistoryPanelPort`
- `ports.AdsPanelPort`
- `messages.Request`

`controller`, `network`, `render`, `state`, `panels` concrete 모듈은 import하지 않는다.

## 모듈 값

- `PYGAME_HIDE_SUPPORT_PROMPT`: pygame import 전에 기본값 `"1"`을 설정하며 기존 환경값은 덮어쓰지 않는다.
- `KEY_DIRECTIONS`: pygame 방향키 상수에서 `up`, `down`, `left`, `right`로의 매핑.

## `ClientApp` 필드

- `config: ConfigPort`: composition root가 넘긴 설정 계약.
- `state: StatePort`: 메인 스레드 상태 계약.
- `analytics_panel: AnalyticsPanelPort`, `history_panel: HistoryPanelPort`: 패널 상태 계약.
- `worker: NetworkPort`: worker 수명주기와 결과 조회 계약.
- `controller: ControllerPort`: 유스케이스 계약.
- `renderer_factory: RendererFactoryPort`: pygame 초기화 뒤 renderer를 만들기 위한 계약.
- `ads_panel: AdsPanelPort | None`: 주입된 광고 상태 계약.
- `_minimized: bool`: 최소화·숨김 이벤트 상태; 초기값 False.

## 메서드

### `ClientApp.__init__(self, config: ConfigPort, state: StatePort, analytics_panel: AnalyticsPanelPort, history_panel: HistoryPanelPort, worker: NetworkPort, controller: ControllerPort, renderer_factory: RendererFactoryPort, ads_panel: AdsPanelPort | None = None, lobby_ads_panel: AdsPanelPort | None = None) -> None`

```text
주입받은 구성 객체·renderer factory·ads_panel·lobby_ads_panel 저장
_minimized=False 설정
pygame 초기화나 worker 시작은 아직 하지 않음
```

### `_control_names(self) -> tuple[str, ...]`

```text
미인증이면 username/password/login control 반환
인증이면 게임 명령, 조회, 로그아웃, 패널 control 반환
하단 카드의 load_refresh/metrics_refresh control 포함
API 응답 보기에는 api_player/api_history/api_windows/api_analytics 포함
통계 패널이 보이면 analytics_summary/analytics_windows 탭 control 추가
idle = 행동 통계·ingest·windows 중 진행 중인 요청이 없음
시간 창 탭이면:
    windows_all/windows_tumbling/windows_sliding 필터 control 추가
    idle이면 windows_refresh 추가
    앞/뒤 페이지가 존재하는 방향의 windows_previous/windows_next 추가
기존 통계 탭이고 idle이면:
    ingest_refresh 추가
    analytics_refresh 추가
```

### `_handle_mouse(self, event, renderer) -> None`

```text
RendererPort.pointer_to_content(event.pos)로 좌표 변환
게시판 패널 존재·인증·통계/이력 비표시·광고 visible이며 controls.get('ad_click')과 충돌하면:
    ControllerPort.request_ad_event(ads_panel, 'click') 호출 후 반환
현재 허용된 control 이름 순회 후 controls[name]과 충돌 검사
입력 필드면 State.focus 변경
게임/조회/패널 control이면 대응 ClientController 메서드 호출
analytics_refresh/api_analytics이면 request_analytics 호출
ingest_refresh이면 request_ingest 호출
windows_refresh/api_windows이면 request_windows 호출
load_refresh/metrics_refresh이면 request_measurement('load'/'metrics') 호출
analytics_summary/analytics_windows이면 select_analytics_view 호출
windows_all/windows_tumbling/windows_sliding이면 select_window_kind 호출
windows_previous/windows_next이면 change_window_page(-1/+1) 호출
refresh는 submit('player'), logout/login은 해당 kind submit
```

탭·종류·페이지 선택은 이미 받은 패널 데이터만 바꾼다. 시간 창 요청은 명시적인 새로 읽기/API 버튼 경로에서만 시작하고 HTTP 완료를 기다리지 않는다. 진행 중 중복 요청의 최종 차단은 [controller.py](controller.py.md)와 [panels.py](panels.py.md)가 담당한다.

### `_handle_keydown(self, event) -> None`

```text
인증 상태:
    방향키 -> request_command('move', direction)
    Z -> request_command('gather')
    X -> request_command('train')
미인증 상태:
    Tab -> 입력 focus 전환
    Backspace -> 현재 입력 마지막 문자 제거
    Enter -> submit('login')
```

### `_handle_event(self, event, renderer) -> None`

```text
QUIT이고 아직 종료 중이 아니면 controller.begin_shutdown()
WINDOWMINIMIZED/WINDOWHIDDEN이면 _minimized=True
WINDOWRESTORED/WINDOWSHOWN이면 _minimized=False
VIDEORESIZE이면 RendererPort.resize(event.w, event.h)
인증 상태의 MOUSEWHEEL이면 RendererPort.scroll(-event.y * 72)
closing/busy가 아니면 mouse/keydown 이벤트를 전용 helper로 전달
미인증 TEXTINPUT이면 printable 문자만 username 150자/password 256자로 제한해 저장
```

### `_drain_results(self) -> None`

```text
NetworkPort.get_result_nowait() 반복
ad_event/ad_event_error이면:
    needs_login이면 controller.apply_result 후 두 광고 패널 clear
    아니고 게시판 패널 존재·인증·비종료이면 apply_event(result, monotonic())
ads_* 결과이면:
    비종료이며 현재 장면에 맞는 슬롯만 적용: 인증이면 게시판, 미인증이면 로비 패널의 apply(result, time.monotonic()) 호출
그 외 controller.apply_result(result)에 전달
    needs_login 또는 logged_out/fatal이면 두 광고 패널 모두 AdsPanelPort.clear()
queue.Empty이면 반환
```

### `run(self) -> int`

```text
pygame display/font 초기화
RendererFactoryPort(config)로 RendererPort 생성
NetworkPort.start()
Clock 생성, 텍스트 입력 시작

반복:
    pygame event를 _handle_event로 처리
    _drain_results()
    closing이고 NetworkPort.is_alive()가 False이면 join 후 반복 종료
    로그인 입력 가능 상태면 RendererPort.text_input_rect로 IME 입력 위치 갱신
    광고 패널이 있으면:
        인증·비종료·비최소화·renderer.ads_visible()·통계/이력 비표시로 visible 계산
        미인증·비종료·비최소화·renderer.ads_visible('lobby-banner')로 lobby_visible 계산
        각 슬롯의 visible/lobby_visible로 AdsPanelPort.begin(time.monotonic(), ...)이 허용하면:
            각 패널별 NetworkPort.submit(Request('ads', request_id=panel.request_id, slot_id=panel.slot_id))
        renderer.draw(state, analytics_panel, history_panel, ads_panel if visible else None)
        lobby_ads_panel이 있으면 draw의 다섯 번째 인자로 lobby_ads_panel if lobby_visible else None 전달
    두 광고 패널 모두 없으면 renderer.draw(state, analytics_panel, history_panel)
    draw/present 완료 후 게시판 존재·인증·비종료·비최소화·광고 visible·통계/이력 비표시이면:
        ControllerPort.request_ad_event(ads_panel, 'impression')
        click_requested이면 ControllerPort.request_ad_event(ads_panel, 'click')로 재시도
    clock.tick(60)

finally:
    password 제거
    NetworkPort가 살아 있으면 stop 요청
    SDL event pump를 유지하며 is_alive()가 False가 될 때까지 대기
    NetworkPort.join()
    텍스트 입력과 pygame 종료

0 반환
```

worker가 살아 있는 동안 UI 스레드에서 바로 `join()`하지 않는 기존 종료 규칙을 유지한다.

## 이벤트 라우팅

```text
pygame event
  -> ClientApp._handle_event
     -> ClientController 유스케이스
        -> State/PanelState
        -> NetworkWorker.submit

NetworkPort.get_result_nowait
  -> ClientApp._drain_results
     -> ad_event/ad_event_error는 apply_event 또는 needs_login 처리
     -> ads_* + AdsPanelPort가 있으면 AdsPanelPort.apply (비종료이며 현재 장면의 슬롯만)
     -> 그 외 ControllerPort.apply_result

ClientApp.run
  -> AdsPanelPort.begin(now, visible)
     -> 허용 시 Request('ads', request_id, slot_id) -> NetworkPort.submit
```

replay 입력이나 replay 결과 경로는 없다.

## 광고 상태 규칙의 소유자

요청 간격·결정 유지·늦은 결과 거부는 [ads_panel.py](ads_panel.py.md), 실제 HTTP·이미지 제한은 [network_ads.py](network_ads.py.md), 이미지 변환과 출력은 [render_ads.py](render_ads.py.md)를 따른다. ClientApp은 위 포트 호출과 queue 분기만 수행한다.

광고 결과는 Result.slot_id에 따라 게시판 또는 로비 패널에만 적용한다. 두 패널의 begin을 각각 호출한다. lobby_ads_panel을 주입한 경우 RendererPort.draw의 다섯 번째 인자로 전달한다. 로그인 전에는 무인증 로비 GET을 요청하고, 로그인 후에는 게시판 광고만 요청한다. 서버가 로그인 전 조회를 지원하지 않으면 안내를 표시한다.
