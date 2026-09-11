# Village Lab 로컬 Python 접속기

Python 3.12, pygame-ce, aiohttp와 표준 라이브러리만 사용합니다. HTTP 로그인과 자기 상태 조회까지 구현하며 게임 규칙, Django view, DB는 변경하지 않습니다. 브라우저/WebView를 사용하지 않습니다.

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

창이 열리면 사용자명과 비밀번호를 입력한 뒤 **접속**을 누릅니다. `Tab`으로 입력칸을 이동하고 `Enter`로 접속할 수도 있습니다. 성공하면 **마을 준비 중** 화면에 자기 player 정보가 표시됩니다. **상태 새로고침**으로 다시 조회하고, **로그아웃**으로 계정 접속을 해제합니다.

창의 닫기 버튼으로 프로그램을 종료합니다. 터미널에서 가상환경을 해제하려면 `deactivate`를 입력하세요.

`ModuleNotFoundError`가 나오면 위 운영체제별 가상환경을 활성화한 상태에서 `python -m pip install -r requirements.txt`를 다시 실행하세요. 연결 실패가 나오면 Django 서버 실행 여부와 `client/config.json`의 주소를 확인하세요.

## 파일과 설정

- `client/main.py`: 메인 스레드의 이벤트, 입력, 결과 큐 처리 및 종료.
- `client/network.py`: 네트워크 worker 하나, asyncio loop 하나, ClientSession 하나. thread-safe Queue로만 명령/결과 전달.
- `client/state.py`: 설정, UI 상태, 비밀 정보를 포함하지 않는 결과 메시지.
- `client/render.py`: Pygame 로그인, 마을 준비 중, player 상태, 읽기 전용 API 패널.
- `client/config.json`: 실제 읽는 설정. 루트에 있던 설정을 복사했으며 루트 `config.json`은 읽지 않습니다.
- `tests/test_client.py`: 표준 unittest와 로컬 aiohttp 모의 서버를 사용하는 계약 검증.

`server_base_url` 기본값은 `http://127.0.0.1:8000`이며 경로 없는 origin이어야 합니다. `window_width`, `window_height`, `tile_size`, `assets_dir`를 읽습니다. `assets_dir: "assets"`는 작업 디렉터리와 관계없이 `client/assets`입니다. 선택적으로 한글 폰트를 `client/assets/font.ttf`에 넣을 수 있으며 없으면 시스템 한글 폰트를 찾습니다. 이번 HTTP 단계에서는 타일 크기만 설정으로 준비하고 타일맵/이미지 자산은 아직 사용하지 않습니다. 이후 이미지 decode와 display도 메인 스레드에서 수행해야 합니다.

## 확인할 서버 계약

| 요청 | 기대하는 응답 / 조건 |
| --- | --- |
| `GET /api/auth/csrf/` | 2xx JSON 객체의 비어 있지 않은 문자열 `csrfToken`, CSRF 쿠키 설정 |
| `POST /api/auth/login/` | JSON `{username,password}`, `X-CSRFToken`, `Origin` 전달. 2xx JSON의 `authenticated`가 불리언 `true` |
| 로그인 직후 `GET /api/auth/csrf/` | 같은 세션에서 회전된 CSRF 토큰 갱신 |
| `GET /api/player/` | 같은 세션의 자기 정보. 최상위 `player_id`, `room_id`는 정수 또는 80자 이하 문자열, `x`, `y`, `coins`, `version`은 정수 |
| `POST /api/auth/logout/` | WS가 있으면 먼저 종료, CSRF 재조회 후 최신 토큰과 Origin 사용. 204 또는 2xx JSON 객체 |

실제 서버가 player 객체를 다른 키 아래 감싸거나 좌표를 실수로 반환한다면 계약을 먼저 맞춰야 합니다. 모든 HTTP 요청은 리다이렉트를 따르지 않고 전체 4초, 연결/읽기 2초 제한을 적용합니다. 302/401은 재로그인 안내, 403은 CSRF/Origin 설정 안내를 표시합니다. HTML과 잘못된 JSON은 상태 데이터로 사용하지 않습니다.

교실 로컬 IP 쿠키를 받기 위해 worker loop 안에서 `CookieJar(unsafe=True)`를 만듭니다. 쿠키와 토큰은 프로세스별 메모리에만 존재합니다. 인증 요청/응답, 비밀번호, 쿠키, CSRF 토큰/헤더를 설정·파일·로그·API 패널에 저장하거나 출력하지 않습니다. 비밀번호는 제출 즉시 입력 필드에서 비우고 요청 완료/취소 시 참조를 제거합니다. Python 문자열의 물리적 메모리 덮어쓰기를 보장하는 구현은 아닙니다.

API 패널은 최근 `GET /api/player/`의 경로, status, 위 여섯 필드로 제한한 JSON만 표시합니다. 임의 경로 입력/요청 기능은 없으며 서버의 추가 필드와 오류 본문은 표시하지 않습니다. 로그아웃 완료/실패 시 로컬 계정과 쿠키를 모두 비우고, 서버 로그아웃을 확인하지 못한 경우 이를 안내합니다.

창 종료 시 진행 중 작업을 취소하고 WS 및 ClientSession을 닫은 후 worker가 종료됩니다. 종료 화면에서도 이벤트 처리를 계속하며 UI에서 네트워크 대기나 `time.sleep()`을 하지 않습니다. 창 종료 자체가 서버 로그아웃 POST를 의미하지는 않습니다.

## 검증

```sh
python -m unittest discover -s tests -v
```

모의 서버에서 로그인 순서, 로컬 쿠키 유지, 회전 토큰, 로그아웃, 서로 다른 worker의 쿠키 격리, 302/401/403, HTML/잘못된 JSON/스키마 거부, timeout 및 진행 중 요청 취소를 검증합니다. 실제 Django 서버 통합은 별도 확인이 필요합니다.

구현 참고: [aiohttp ClientSession / CookieJar](https://docs.aiohttp.org/en/stable/client_reference.html), [pygame-ce 텍스트 입력](https://pyga.me/docs/ref/key.html).
