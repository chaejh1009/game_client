# Replay Client

`data-replay/raw/game-events.jsonl`을 읽어 게임 화면의 플레이어 이동과 채굴 행위를 순서대로 재생하는 독립형 Pygame 클라이언트입니다.

이 클라이언트는 서버, 로그인, WebSocket, Django 실행 없이 로컬 JSONL 파일만으로 동작합니다.

## 실행

프로젝트 루트(`/Users/chaejonghun/chapter3/game_client`)에서 실행합니다.

```sh
client/.venv/bin/python replay_client/main.py
```

기본 경로는 `replay_client/config.json`의 `data_path`로 지정되어 있습니다. 다른 JSONL을 바로 열려면 다음처럼 실행할 수 있습니다.

```sh
client/.venv/bin/python replay_client/main.py --data /path/to/another-events.jsonl
```

`pygame-ce`가 없는 환경에서는 아래처럼 이 클라이언트 전용 의존성만 설치하세요.

```sh
client/.venv/bin/python -m pip install -r replay_client/requirements.txt
```

## 조작

- 파일을 불러오면 첫 이벤트부터 자동 재생합니다. `재생 / 일시정지`: 이벤트를 순서대로 적용합니다. 기본 간격은 0.24초이며 0.5x~8x로 조절할 수 있습니다.
- `이전 / 다음`, `처음 / 끝`: 한 이벤트씩 이동하거나 처음·마지막 상태로 이동합니다.
- 타임라인 행 클릭: 해당 이벤트까지 즉시 상태를 재구성하고 편집기에 표시합니다.
- 이벤트 편집기: `event_type`, `player_id`, `room_id`, 좌표, 코인, 버전을 수정한 뒤 `적용`합니다.
- `복제`, `새 이벤트`, `삭제`: 현재 JSONL을 메모리에서 편집합니다.
- 상단 경로 입력: 다른 JSONL 파일 경로를 입력하고 `불러오기`를 누릅니다.
- `Ctrl+S`: 편집본을 저장합니다.

편집 저장 기본 위치는 `replay_client/replay-edited.jsonl`입니다. 원본 `game-events.jsonl`은 기본 동작으로 덮어쓰지 않습니다. 저장한 편집본을 이어서 작업하려면 상단 경로에 해당 파일을 불러오면 됩니다.

## 화면

- 왼쪽 `REPLAY STAGE`: 타일 맵, 플레이어 위치, 코인, 이동 경로
- 오른쪽 `EVENT TIMELINE`: 전체 이벤트 목록과 검색
- 오른쪽 `EVENT EDITOR`: 선택 이벤트의 편집 가능한 핵심 필드

기존 `client/` 실시간 접속기는 수정하지 않았습니다. 기존 타일과 캐릭터 이미지는 `config.json`의 `asset_dir`로 참조하며, 이미지가 없어도 색상 기반 대체 화면으로 실행됩니다.
