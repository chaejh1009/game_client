"""Main-thread ad state, scheduling and stale result rejection; no I/O."""
from dataclasses import dataclass, field

from messages import Result


@dataclass
class AdsPanelState:
    slot_id: str = 'village-board'
    decision: dict = field(default_factory=dict)
    image_bytes: bytes = field(default=b'', repr=False)
    image_status: str = '대기'
    displayed: bool = False
    pending: bool = False
    request_id: int = 0
    last_request: float = float('-inf')
    retained_until: float = 0
    message: str = '광고 선택 대기'

    def clear(self) -> None:
        self.request_id += 1  # Invalidate queued results across logout/relogin.
        self.decision = {}
        self.image_bytes = b''
        self.image_status = '대기'
        self.displayed = self.pending = False
        self.last_request = float('-inf')
        self.retained_until = 0
        self.message = '광고 선택 대기'

    def begin(self, now: float, visible: bool) -> bool:
        if (not visible or self.pending or self.image_status == 'bytes 준비'
                or now - self.last_request < 15 or now < self.retained_until):
            return False
        self.request_id += 1
        self.last_request = now
        self.pending = True
        return True

    def apply(self, result: Result, now: float) -> bool:
        if not result.kind.startswith('ads_'):
            return False
        if result.slot_id != self.slot_id or result.request_id != self.request_id or not self.pending:
            return True
        if result.kind == 'ads_decision':
            self.decision = result.ad or {}
            self.image_bytes = b''
            self.displayed = False
            self.retained_until = now + 10
            self.image_status = '없음' if self.decision.get('empty') else '다운로드 중'
            self.message = '등록된 광고 없음' if self.decision.get('empty') else '이미지 준비 중'
            if self.decision.get('empty'):
                self.pending = False
        elif result.kind == 'ads_text':
            if result.decision_id == str(self.decision.get('decision_id', '')):
                self.pending = False
                self.image_ready(True)
        elif result.kind in ('ads_image', 'ads_image_error'):
            if result.decision_id != str(self.decision.get('decision_id', '')):
                return True
            self.pending = False
            self.image_bytes = result.image_bytes
            self.image_status = 'bytes 준비' if result.kind == 'ads_image' else '실패'
            self.message = '이미지 변환 대기' if result.kind == 'ads_image' else result.message
        elif result.kind == 'ads_error':
            self.pending = False
            self.message = result.message
        return True

    def image_ready(self, success: bool) -> None:
        self.image_status = '준비' if success else '실패'
        self.message = '표시 대기' if success else '이미지 실패 · 제목 안내만 표시'
        self.displayed = False

    def mark_displayed(self, now: float) -> None:
        if self.image_status == '준비' and not self.displayed:
            self.displayed = True
            self.message = '표시 완료'
            self.retained_until = max(self.retained_until, now + 10)
