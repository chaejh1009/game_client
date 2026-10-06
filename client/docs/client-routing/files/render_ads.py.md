# `client/render_ads.py`

## 책임과 경계

게시판 옆 광고 Rect에서 서버 제목·이미지와 비밀값 없는 확인 항목을 출력한다. 모든 호출은 메인 스레드다. 직접 호출은 BytesIO, pygame.image.load/Surface.convert_alpha/transform.smoothscale/Rect/blit, RenderSupport의 text/wrapped, AdsPanelPort.image_ready다. 네트워크나 POST를 수행하지 않는다.

## `AdsRenderer`

- `__init__()`: 최근 결정·bytes 키와 Surface cache 초기화.
- `draw(view, panel) -> bool`: 결정 ID/bytes identity가 달라지면 cache 제거 -> bytes가 있으면 BytesIO→image.load→1600만 pixel 상한 검사→convert_alpha→카드 크기 내 비율 유지 smoothscale -> panel.image_ready 성공/실패 호출 -> 카드 Rect/제목 두 줄 clip -> 준비 Surface가 있으면 blit, 없으면 이미지 준비/실패 안내 -> 결정 ID·캠페인·슬롯·모의 포인트·이미지 준비·표시 상태만 출력 -> clip 복원 -> 실제 이미지 blit 여부 반환.

empty=true는 `등록된 광고 없음`이며 이미지 실패에서는 서버 title만 안내하고 blit 성공을 반환하지 않는다. 첫 frame의 표시 상태는 미표시이고, [render.py](render.py.md)가 present/flip 후 mark_displayed한 다음 frame에서 완료로 보인다. 창 크기·viewport와 ad_rect는 [render_support.py](render_support.py.md)가 소유한다. `client/assets` 타일 로딩에 광고 bytes를 저장하거나 섞지 않는다.
