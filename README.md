# Village Lab 로컬 Python 게임 클라이언트

Python 3.12, pygame-ce, aiohttp와 표준 라이브러리로 동작하는 데스크톱 클라이언트입니다. Django 세션 로그인, 자기 player 상태 조회, WebSocket 게임 명령(이동·채굴·개인 수련)을 지원하며 게임 규칙, Django view, DB는 변경하지 않습니다. 브라우저/WebView를 사용하지 않습니다.

## 행동데이터 재생기 (서버 불필요)

기록된 `/Users/chaejonghun/chapter3/data-replay/raw/game-events.jsonl`을 화면으로 재생하려면 기존 접속기인 `client/main.py`가 아니라 아래 재생기를 실행하세요. 서버·로그인·WebSocket이 필요 없습니다.

```sh
cd /Users/chaejonghun/chapter3/game_client
client/.venv/bin/python replay_client/main.py
```

정상 실행 시 창 제목은 `Replay Client · 행동데이터 재생`이고 `EVENT TIMELINE`, `EVENT EDITOR` 패널이 보입니다. 자세한 조작은 [`replay_client/README.md`](replay_client/README.md)를 참고하세요.

로그인 후에는 20×15 타일 마을, 길, 나무·집 장식, 플레이어 스프라이트를 Pygame 화면에 표시합니다. WebSocket으로 받은 같은 방의 접속자 목록과 위치 변경을 실시간으로 반영하며, 내 플레이어는 초록색 표식, 다른 플레이어는 노란색 표식과 player ID로 구분합니다.

## 현재 기능

| 기능 | 조작 | 설명 |
| --- | --- | --- |
| 이동 | 방향키 또는 화면의 방향 버튼 | 서버의 이동 규칙과 맵 경계 검증을 따릅니다. |
| 코인 채굴 | `Z` 키 또는 **Z 채굴** 버튼 | 서버가 허용하는 채굴 지점 `(2, 2)`에서만 성공합니다. |
| 개인 수련 | `(3, 2)`에서 `X` 키 또는 **X 수련** 버튼 | 서버가 확정한 내 위치가 수련 타일이고 WS가 연결됐으며 대기 중인 명령이 없을 때만 실행됩니다. 키 입력이나 클릭 한 번에 한 번만 요청합니다. |
| 상태 조회 | **새로고침** | `GET /api/player/`로 자기 상태를 다시 가져옵니다. |
| API 응답 보기 | **/api/player/** 또는 **/api/history/** | 현재 상태 또는 로그인한 플레이어의 최근 행동 20개를 조회합니다. |
| 수련 이력 | **수련 이력** | 수련 뒤 데이터는 자동 갱신하지만 패널은 자동으로 열지 않습니다. 버튼을 눌렀을 때 최근 행동의 종류·시각과 transition의 step·reward를 표시합니다. |
| 같은 방 플레이어 | 자동 갱신 | WebSocket snapshot과 상태 방송을 계속 받아 접속·퇴장·이동을 표시합니다. |
| 접속 해제 | **로그아웃** | WebSocket을 먼저 닫은 뒤 Django 로그아웃을 요청합니다. |

이동·채굴·수련은 한 명령의 응답을 기다린 뒤 다음 명령을 보내며, 세 종류를 합쳐 0.2초에 한 번만 전송합니다. 동전과 성공 상태는 서버가 같은 `command_id`로 확정한 내 state를 받은 뒤에만 갱신됩니다.

## 실행 전 준비

Python **3.12**를 설치하고, `client` 폴더와 `requirements.txt`가 있는 프로젝트 폴더에서 명령을 실행하세요. 아래 경로는 예시이므로 실제 저장 위치로 바꿉니다. 프로젝트 이름이 `village_lab`이면 그 폴더를, 현재 작업 환경에서는 `game_client` 폴더를 사용합니다.

로그인하려면 Django 서버가 별도로 실행 중이어야 하며 서버에 등록된 계정이 필요합니다. 접속기 실행 명령은 서버를 함께 실행하지 않습니다.

- 서버가 같은 컴퓨터에 있으면 `client/config.json`의 `server_base_url` 기본값 `http://127.0.0.1:8000`을 사용합니다.
- 교실의 다른 컴퓨터가 서버라면 담당자가 알려 준 주소로 바꿉니다. 예: `http://192.168.0.10:8000`. `127.0.0.1`은 접속기를 실행하는 컴퓨터 자신을 뜻합니다.
- 가상환경 `client/.venv`는 운영체제나 컴퓨터 사이에 복사해서 사용하지 말고 각 컴퓨터에서 생성하세요.

## Windows에서 실행

**명령 프롬프트(cmd)**를 열고 실행하세요. 아래 활성화 명령은 cmd 기준입니다.

### 처음 한 번: 설치 및 실행

```bat
cd /d "C:\프로젝트경로\village_lab"
py -3.12 --version
py -3.12 -m venv client\.venv
client\.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python client/main.py
```

버전 확인 결과가 `Python 3.12.x`인지 확인하세요. `py` 명령을 찾지 못하면 Python 3.12 및 Python Launcher 설치 여부를 확인하고 터미널을 다시 여세요.

### 다음부터 실행

```bat
cd /d "C:\프로젝트경로\village_lab"
client\.venv\Scripts\activate.bat
python client/main.py
```

**PowerShell**을 사용한다면 가상환경 활성화 없이 아래처럼 실행할 수도 있습니다. 이 방법은 활성화 스크립트 실행 정책 변경이 필요하지 않습니다.

```powershell
cd "C:\프로젝트경로\village_lab"
# 처음 한 번만 실행
py -3.12 -m venv client/.venv
.\client\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 다음부터는 폴더 이동 후 이 명령만 실행
.\client\.venv\Scripts\python.exe client/main.py
```

## macOS에서 실행

**터미널** 앱을 열고 실행하세요.

### 처음 한 번: 설치 및 실행

```sh
cd "/프로젝트경로/village_lab"
python3.12 --version
python3.12 -m venv client/.venv
source client/.venv/bin/activate
python -m pip install -r requirements.txt
python client/main.py
```

버전 확인 결과가 `Python 3.12.x`인지 확인하세요. `python3.12` 명령을 찾지 못하면 Python 3.12 설치 여부를 확인하고 터미널을 다시 여세요.

### 다음부터 실행

```sh
cd "/프로젝트경로/village_lab"
source client/.venv/bin/activate
python client/main.py
```

현재 작업 중인 Mac에는 가상환경과 의존성이 준비되어 있으므로 다음 명령으로 실행하면 됩니다.

```sh
cd /Users/chaejonghun/chapter3/game_client
source client/.venv/bin/activate
python client/main.py
```

## 접속 및 종료

창이 열리면 사용자명과 비밀번호를 입력한 뒤 **접속**을 누릅니다. `Tab`으로 입력칸을 이동하고 `Enter`로 접속할 수도 있습니다. 로그인 입력 화면에서는 게임 명령이 전송되지 않습니다. 로그인에 성공하면 작은 마을 화면에 자기 player 정보와 맵이 표시됩니다. 방향키 또는 화면의 네 방향 버튼으로 이동하고, `(2, 2)`의 채굴 지점에서는 `Z` 키나 **Z 채굴** 버튼을 누릅니다. `(3, 2)`의 작은 표지 옆에서는 `X` 키나 활성화된 **X 수련** 버튼을 누릅니다. 수련 성공 뒤 같은 로그인 세션으로 최근 이력을 자동 조회하지만 패널은 열지 않습니다. 보고 싶을 때 **수련 이력** 버튼을 누릅니다. **새로고침**으로 HTTP 상태를 다시 조회하고, **로그아웃**으로 계정 접속을 해제합니다.

창의 닫기 버튼으로 프로그램을 종료합니다. 터미널에서 가상환경을 해제하려면 `deactivate`를 입력하세요.

`ModuleNotFoundError`가 나오면 위 운영체제별 가상환경을 활성화한 상태에서 `python -m pip install -r requirements.txt`를 다시 실행하세요. 연결 실패가 나오면 Django 서버 실행 여부와 `client/config.json`의 주소를 확인하세요.

## 파일과 설정

- `client/main.py`: 메인 스레드의 이벤트, 입력, 결과 큐 처리 및 종료.
- `client/network.py`: 네트워크 worker 하나, asyncio loop 하나, ClientSession 하나. HTTP 로그인·상태 조회·로그아웃과 WebSocket 연결·명령을 처리하고 thread-safe Queue로만 명령/결과 전달.
- `client/state.py`: 설정, UI 상태, 비밀 정보를 포함하지 않는 결과 메시지.
- `client/panels.py`: API 응답, Spark 통계, 수련 이력 패널의 메인 스레드 상태.
- `client/render.py`: 메인 스레드의 Pygame 로그인 화면, 20×15 마을 맵, 타일·스프라이트, 명령 버튼, 읽기 전용 state 패널.
- `client/config.json`: 실제 읽는 설정. 루트 `config.json`은 읽지 않습니다.
- `client/assets/`: 기본 타일·장식·플레이어 이미지(`grass.png`, `path.png`, `tree.png`, `house.png`, `hero.png`)와 Kenney 원본 패키지. 원본 패키지의 사용 조건은 각 폴더의 `License.txt`를 확인하세요.
- `tests/test_client.py`: 표준 unittest와 로컬 aiohttp 모의 서버를 사용하는 계약 검증.

주요 `client/config.json` 설정은 다음과 같습니다.

| 키 | 기본값 | 설명 |
| --- | --- | --- |
| `server_base_url` | `http://127.0.0.1:8000` | 경로·쿼리·인증 정보가 없는 HTTP(S) origin입니다. |
| `window_width`, `window_height` | `960`, `720` | 창 크기입니다. 각각 640~3840, 600~2160 범위의 정수여야 합니다. |
| `tile_size` | `32` | 8~128 범위의 정수로 검증됩니다. 현재 맵 렌더러는 32px 타일을 사용합니다. |
| `assets_dir` | `assets` | 기본 자산 폴더 설정입니다. 실제 파일은 아래의 개별 `*_path` 값을 사용합니다. |
| `grass_path`, `path_path`, `tree_path`, `house_path`, `hero_path` | `assets/<name>.png` | `client/config.json` 기준 상대 경로이며 `client` 폴더 밖을 가리킬 수 없습니다. 현재 이미지는 16×16 PNG를 읽어 32×32로 확대합니다. |
| `font_path` | `null` | 선택적인 한글 폰트 경로입니다. 지정하지 않으면 시스템 폰트를 찾고, 없으면 Pygame 기본 폰트로 대체합니다. |

이미지나 폰트가 없거나 형식이 맞지 않으면 프로그램은 색상·기본 폰트로 대체해 실행하고 화면에 자산 오류를 표시합니다. 타일 이미지 decode와 화면 출력은 모두 Pygame 메인 스레드에서 수행합니다.

## 확인할 서버 계약

| 요청 | 기대하는 응답 / 조건 |
| --- | --- |
| `GET /accounts/login/` | Django 로그인 HTML을 반환하고 CSRF 쿠키 설정 |
| `POST /accounts/login/` | 폼 데이터 `{username,password}`, `X-CSRFToken`, `Origin`, `Referer` 전달. 성공 시 30x 리다이렉트와 세션 쿠키 설정 |
| `GET /api/player/` | 같은 세션의 자기 정보. 최상위 `player_id`, `room_id`는 정수 또는 80자 이하 문자열, `x`, `y`, `coins`, `version`은 정수 |
| `GET /api/history/` | 로그인한 플레이어의 최근 이벤트 20개. 이벤트의 `event_type`, `event_time`, `payload.transition.step`, `payload.transition.reward`를 수련 이력 패널에 표시하며 transition이 없는 과거 행도 허용합니다. |
| `WS /ws/play/` | 로그인 세션으로 연결하고, 최초 player state와 `{type:"snapshot",players:[...]}` 및 방의 player state 방송을 계속 받습니다. 이동은 `{type:"move",direction,command_id}`, 채굴은 `{type:"gather",command_id}`, 수련은 `{type:"train",command_id}`만 전송합니다. 자기 player의 응답 중 일치하는 `command_id`만 대기 명령을 완료하고, 다른 player state는 대기 상태에 영향을 주지 않습니다. 한 명령 응답 대기 및 모든 입력을 합쳐 0.2초 간격 적용 |
| `POST /accounts/logout/` | WS가 있으면 먼저 종료하고 회전된 최신 CSRF 쿠키와 Origin을 사용. 200/204 또는 30x 리다이렉트 |

실제 서버가 player 객체를 다른 키 아래 감싸거나 좌표를 실수로 반환한다면 계약을 먼저 맞춰야 합니다. 모든 HTTP 요청은 리다이렉트를 따르지 않고 전체 4초, 연결/읽기 2초 제한을 적용합니다. 302/401은 재로그인 안내, 403은 CSRF/Origin 설정 안내를 표시합니다. HTML과 잘못된 JSON은 상태 데이터로 사용하지 않습니다.

교실 로컬 IP 쿠키를 받기 위해 worker loop 안에서 `CookieJar(unsafe=True)`를 만듭니다. 쿠키와 토큰은 프로세스별 메모리에만 존재합니다. 인증 요청/응답, 비밀번호, 쿠키, CSRF 토큰/헤더를 설정·파일·로그·API 패널에 저장하거나 출력하지 않습니다. 비밀번호는 제출 즉시 입력 필드에서 비우고 요청 완료/취소 시 참조를 제거합니다. Python 문자열의 물리적 메모리 덮어쓰기를 보장하는 구현은 아닙니다.

API 패널은 `GET /api/player/`와 `GET /api/history/` 중 선택한 경로, status, 허용된 필드로 제한한 JSON만 표시합니다. 임의 경로 입력/요청 기능은 없으며 서버의 추가 필드와 오류 본문은 표시하지 않습니다. 수련 성공 뒤의 이력 조회도 같은 worker의 같은 `ClientSession`을 사용하고 결과만 queue로 메인 스레드에 전달합니다. 로그아웃 완료/실패 시 로컬 계정과 쿠키를 모두 비우고, 서버 로그아웃을 확인하지 못한 경우 이를 안내합니다.

창 종료 시 진행 중 작업을 취소하고 WS 및 ClientSession을 닫은 후 worker가 종료됩니다. 종료 화면에서도 이벤트 처리를 계속하며 UI에서 네트워크 대기나 `time.sleep()`을 하지 않습니다. 창 종료 자체가 서버 로그아웃 POST를 의미하지는 않습니다.

## 검증

```sh
python -m unittest discover -s tests -v
```

모의 서버에서 로그인 순서, 로컬 쿠키 유지, WebSocket snapshot·다른 플레이어 방송·명령 응답 매칭, 공유 명령 제한, 로그인 포커스 이동 차단, 회전 토큰, 로그아웃, 서로 다른 worker의 쿠키 격리, 302/401/403, HTML/잘못된 JSON/스키마 거부, timeout 및 진행 중 요청 취소를 검증합니다. 실제 Django 서버 통합은 별도 확인이 필요합니다.

구현 참고: [aiohttp ClientSession / CookieJar](https://docs.aiohttp.org/en/stable/client_reference.html), [pygame-ce 텍스트 입력](https://pyga.me/docs/ref/key.html).
