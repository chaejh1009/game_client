"""Main-thread creative decoding and drawing beside the village board."""
from io import BytesIO

import pygame

from ports import AdsPanelPort
from render_support import CARD, INK, MUTED, ACCENT


class AdsRenderer:
    def __init__(self):
        self._key = None
        self._surface = None

    def draw(self, view, panel: AdsPanelPort, rect=None) -> bool:
        rect = rect if rect is not None else view.ad_rect
        key = (str(panel.decision.get('decision_id', '')),
               id(panel.image_bytes))
        if key != self._key:
            self._key = key
            self._surface = None
            if panel.image_bytes:
                try:
                    image = pygame.image.load(BytesIO(panel.image_bytes))
                    if image.get_width() * image.get_height() > 16_000_000:
                        raise ValueError('image dimensions')
                    image = image.convert_alpha()
                    size = image.get_rect().fit(pygame.Rect(0, 0, rect.width - 24, 82)).size
                    self._surface = pygame.transform.smoothscale(image, size)
                    panel.image_ready(True)
                except (pygame.error, ValueError, OSError):
                    panel.image_ready(False)
        previous = view.screen.get_clip()
        view.screen.set_clip(rect)
        pygame.draw.rect(view.screen, CARD, rect, border_radius=10)
        pygame.draw.rect(view.screen, ACCENT, rect, width=1, border_radius=10)
        data = panel.decision
        if panel.slot_id == 'village-board':
            view.controls['ad_click'] = pygame.Rect(rect.x + 12, rect.y + 30, rect.width - 24, 128)
        view.text('로비 광고' if panel.slot_id == 'lobby-banner' else '마을 게시판 광고', (rect.x + 12, rect.y + 8), ACCENT, view.small)
        title = ('등록된 광고 없음' if data.get('empty') else data.get('title', panel.message))
        view.screen.set_clip(pygame.Rect(rect.x + 12, rect.y + 30, rect.width - 24, 40))
        view.wrapped(title, rect.x + 12, rect.y + 30, rect.width - 24, font=view.small)
        view.screen.set_clip(rect)
        blitted = self._surface is not None and panel.image_status == '준비'
        if blitted:
            view.screen.blit(self._surface, (rect.x + (rect.width - self._surface.get_width()) // 2,
                                            rect.y + 76))
        elif not (data.get('body') and panel.image_status == '준비'):
            view.text(panel.image_status, (rect.x + 12, rect.y + 98), MUTED, view.small)
        if not panel.image_bytes and data.get('body') and panel.image_status == '준비':
            view.screen.set_clip(pygame.Rect(rect.x + 12, rect.y + 76, rect.width - 24, 82))
            view.wrapped(data['body'], rect.x + 12, rect.y + 76, rect.width - 24,
                         font=view.small)
            view.screen.set_clip(rect)
            blitted = True
        view.text(f"모의 포인트: {data.get('bid_units', '—')}",
                  (rect.x + 12, rect.y + 166), INK, view.small)
        if panel.slot_id == 'village-board':
            label = ('광고 새 요청 필요' if panel.event_rejected else
                     f"노출 {'완료' if panel.impression_ok else '대기'} · 클릭 {'완료' if panel.click_ok else '대기'}")
            view.text(label,
                      (rect.x + 12, rect.y + 185), MUTED, view.small)
            status = (panel.event_error.split(' 광고 새 요청 필요', 1)[0]
                      if panel.event_rejected else panel.message)
            if len(status) > 23:
                status = status[:22] + '…'
            view.text(status, (rect.x + 12, rect.y + 202), MUTED, view.tiny)
        else:
            view.wrapped(panel.message, rect.x + 12, rect.y + 187, rect.width - 24,
                         font=view.small, color=MUTED)
        view.screen.set_clip(previous)
        return blitted
