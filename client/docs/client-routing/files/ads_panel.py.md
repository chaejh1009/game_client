# `client/ads_panel.py`

## 책임과 경계

메인 스레드 광고 상태와 요청 간격·결정 유지·늦은 결과 거부만 소유한다. HTTP/pygame/I/O는 없으며 messages.Result만 읽는다. AdsPanelPort의 구조적 구현이다.

## `AdsPanelState`

AdsPanelPort를 구현하는 메인 스레드 상태 dataclass다.

## 필드

slot_id는 패널의 광고 슬롯(기본 village-board)이다. decision은 허용 광고 필드, image_bytes는 repr 제외 공개 bytes, image_status/displayed/message는 GUI 안내다. pending/request_id는 요청 진행·세대, last_request는 monotonic 요청 시작 시각, retained_until은 다음 교체 가능 시각이다. 초기 last_request는 -inf다. 게임 coins와 별개다.

## 메서드

- `clear()`: request_id 증가 -> 결정·bytes·표시/진행/시각 초기화. 이전 계정에서 온 결과를 무효화한다.
- `begin(now, visible) -> bool`: 비표시·pending·미변환 bytes·요청 후 15초 미만·retained_until 이전이면 False -> 요청 세대 증가, last_request/pending 갱신 -> True. 호출자는 Request를 queue에 제출한다.
- `apply(result, now) -> bool`: ads_* 외 False -> slot_id 또는 request_id 불일치/진행 아님이면 소비만 하고 무시 -> ads_decision이면 결정/bytes/표시 초기화, 10초 유지, empty 안내/완료 또는 다운로드 상태 -> ads_text는 현재 decision_id 일치 시 pending 해제·준비 상태로 전환 -> ads_image/ads_image_error는 현재 decision_id 일치 시에만 bytes/오류 적용하고 pending 해제 -> ads_error면 pending 해제·안내 갱신. 항상 게임 State와 분리한다.
- `image_ready(success)`: 메인 스레드 변환 성공이면 준비/표시 대기, 실패이면 제목 안내·실패 -> displayed=False.
- `mark_displayed(now)`: 준비 상태의 첫 flip 완료일 때만 displayed=True -> 표시 완료 안내 -> retained_until을 최소 now+10으로 연장.
