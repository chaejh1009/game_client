# `client/config.json`

## 책임과 경계

`state.Config.load()`가 실행 시 읽는 클라이언트 설정 원본이다. 서버 동작이나 API 계약을 정의하지 않으며, 모든 상대경로는 `client/` 기준이다.

## 키와 값

| 키 | 현재 값 | 소비자와 의미 |
|---|---:|---|
| `server_base_url` | `http://127.0.0.1:8000` | `Config.load`가 경로 없는 HTTP(S) origin으로 검증하고 `NetworkWorker`에 전달 |
| `window_width` | `960` | `Renderer` 창 너비; 허용 범위 640~3840 |
| `window_height` | `720` | `Renderer` 창 높이; 허용 범위 600~2160 |
| `tile_size` | `32` | 설정 모델에 보존되는 타일 크기; 허용 범위 8~128 |
| `assets_dir` | `assets` | client 내부 자산 디렉터리 경로 |
| `grass_path` | `assets/grass.png` | `Renderer._prepare_assets`의 잔디 이미지 |
| `path_path` | `assets/path.png` | 길 이미지 |
| `tree_path` | `assets/tree.png` | 나무 sprite |
| `house_path` | `assets/house.png` | 집 sprite |
| `hero_path` | `assets/hero.png` | player sprite |
| `font_path` | `null` | 시스템 한글 글꼴 탐색 사용; 문자열이면 client 내부 파일만 허용 |

## 로드 의사코드

```text
main.main()
  -> Config.load()
     -> 이 JSON 읽기
     -> origin/크기/경로 검증 및 정규화
  -> Renderer(config): 화면 크기와 자산 경로 소비
  -> NetworkWorker(config.server_base_url): 서버 origin 소비
```

`assets_dir` 아래 정적 파일은 코드 호출 계층이 아니며, 위 경로 키를 통해서만 런타임 라우팅에 참여한다.

