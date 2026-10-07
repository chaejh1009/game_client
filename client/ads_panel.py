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
    impression_pending: bool = False
    impression_ok: bool = False
    click_pending: bool = False
    click_ok: bool = False
    click_requested: bool = False
    event_retry_at: float = 0
    event_error: str = ''
    event_rejected: bool = False

    def reset_events(self) -> None:
        self.impression_pending = self.impression_ok = False
        self.click_pending = self.click_ok = self.click_requested = False
        self.event_retry_at = 0
        self.event_error = ''
        self.event_rejected = False

    def apply_event(self, result: Result, now: float) -> None:
        if (result.slot_id != self.slot_id or result.request_id != self.request_id
                or result.decision_id != str(self.decision.get('decision_id', ''))
                or result.event_type not in ('impression', 'click')):
            return
        kind = result.event_type
        if not getattr(self, kind + '_pending'):
            return
        setattr(self, kind + '_pending', False)
        data = result.ad_event
        valid = (
            result.kind == 'ad_event' and isinstance(data, dict)
            and data.get('event_id') == result.decision_id + ':' + kind
            and data.get('event_type') == kind
            and type(data.get('created')) is bool)
        if valid:
            setattr(self, kind + '_ok', True)
            self.event_error = ''
            self.message = '노출 저장 완료 · 광고 클릭 가능' if kind == 'impression' else '클릭 저장 완료'
        else:
            self.event_error = result.message or '광고 실적 확인 실패'
            self.message = self.event_error
            self.event_rejected = result.event_rejected
            if self.event_rejected:
                self.click_requested = False
                self.message = '광고 새 요청 필요'
                self.retained_until = now + 2
                self.last_request = now - 15
            else:
                self.event_retry_at = now + 2

    def clear(self) -> None:
        self.request_id += 1  # Invalidate queued results across logout/relogin.
        self.decision = {}
        self.image_bytes = b''
        self.image_status = '대기'
        self.displayed = self.pending = False
        self.last_request = float('-inf')
        self.retained_until = 0
        self.message = '광고 선택 대기'
        self.reset_events()

    def begin(self, now: float, visible: bool) -> bool:
        if (not visible or self.pending or self.image_status == 'bytes 준비'
                or self.impression_pending or self.click_pending
                or (not self.event_rejected and self.slot_id == 'village-board'
                    and self.displayed and not self.impression_ok)
                or (not self.event_rejected and self.click_requested and not self.click_ok)
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
            self.reset_events()
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
