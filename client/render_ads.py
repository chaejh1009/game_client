"""Main-thread creative decoding and drawing beside the village board."""
from io import BytesIO

import pygame

from ports import AdsPanelPort
from render_support import CARD, INK, MUTED, ACCENT


class AdsRenderer:
    def __init__(self):
        self._key = None
        self._surface = None

    def draw(self, view, panel: AdsPanelPort) -> bool:
        rect = view.ad_rect
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
        view.text('마을 게시판 광고', (rect.x + 12, rect.y + 8), ACCENT, view.small)
        title = ('등록된 광고 없음' if data.get('empty') else data.get('title', panel.message))
        view.screen.set_clip(pygame.Rect(rect.x + 12, rect.y + 30, rect.width - 24, 40))
        view.wrapped(title, rect.x + 12, rect.y + 30, rect.width - 24, font=view.small)
        view.screen.set_clip(rect)
        blitted = self._surface is not None and panel.image_status == '준비'
        if blitted:
            view.screen.blit(self._surface, (rect.x + (rect.width - self._surface.get_width()) // 2,
                                            rect.y + 76))
        else:
            view.text(panel.image_status, (rect.x + 12, rect.y + 98), MUTED, view.small)
        rows = (
            f"결정 ID: {data.get('decision_id', '—')}",
            f"캠페인: {data.get('campaign_id', '—')}",
            f"슬롯: {data.get('slot_id', 'village-board')}",
            f"모의 포인트: {data.get('bid_units', '—')}",
            f"이미지 준비: {panel.image_status}",
            f"표시 상태: {'표시 완료' if panel.displayed and blitted else '미표시'}",
        )
        for index, row in enumerate(rows):
            view.text(row, (rect.x + 12, rect.y + 166 + index * 19), INK, view.small)
        view.screen.set_clip(previous)
        return blitted
