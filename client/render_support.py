"""Shared pygame resources, layout, and drawing primitives for the render layer."""
from typing import Any

import pygame

from ports import ConfigPort


BG = (17, 25, 35)
CARD = (27, 39, 51)
INK = (230, 238, 238)
MUTED = (155, 178, 186)
ACCENT = (107, 218, 174)
PENDING = (241, 190, 83)
ERROR = (235, 112, 112)
TRAIN = (113, 166, 255)
GRASS_FALLBACK = (92, 154, 78)
PATH_FALLBACK = (206, 158, 99)
TILE_SIZE = 32
MAP_COLUMNS = 20
MAP_ROWS = 15
CONFIRMED_IMAGE_SIZE = (16, 16)


class RenderSupport:
    """Own pygame resources and mechanical drawing operations."""

    def __init__(self, config: ConfigPort) -> None:
        self.config = config
        self.screen = pygame.display.set_mode((config.window_width, config.window_height))
        pygame.display.set_caption('Village Lab · 로컬 접속기')
        self.asset_errors: list[str] = []
        self._prepare_fonts()
        self._prepare_assets()
        self._prepare_layout()

    def _prepare_fonts(self) -> None:
        font_path = self.config.font_path
        if font_path is None or not font_path.is_file():
            self.asset_errors.append('font_path를 client/config.json에 지정하세요.')
            font_path = pygame.font.match_font(
                'applesdgothicneo,malgungothic,nanumgothic,notosanscjkkr')
        try:
            self.font = pygame.font.Font(str(font_path) if font_path else None, 19)
            self.small = pygame.font.Font(str(font_path) if font_path else None, 14)
            self.tiny = pygame.font.Font(str(font_path) if font_path else None, 12)
            self.title = pygame.font.Font(str(font_path) if font_path else None, 30)
        except (OSError, pygame.error):
            self.asset_errors.append('font_path의 폰트를 열 수 없습니다.')
            self.font = pygame.font.Font(None, 19)
            self.small = pygame.font.Font(None, 14)
            self.tiny = pygame.font.Font(None, 12)
            self.title = pygame.font.Font(None, 30)

    def _prepare_assets(self) -> None:
        paths = {
            'grass': self.config.grass_path,
            'path': self.config.path_path,
            'tree': self.config.tree_path,
            'house': self.config.house_path,
            'hero': self.config.hero_path,
        }
        self.assets: dict[str, pygame.Surface | None] = {}
        for name, path in paths.items():
            try:
                image = pygame.image.load(path).convert_alpha()
                if image.get_size() != CONFIRMED_IMAGE_SIZE:
                    raise ValueError('unexpected image size')
                self.assets[name] = pygame.transform.scale(image, (TILE_SIZE, TILE_SIZE))
            except (OSError, ValueError, pygame.error):
                self.assets[name] = None
                self.asset_errors.append(f'{name} 이미지 로딩 실패')

    def _prepare_layout(self) -> None:
        width = self.config.window_width
        self.map_rect = pygame.Rect(24, 128, MAP_COLUMNS * TILE_SIZE, MAP_ROWS * TILE_SIZE)
        sidebar_x = self.map_rect.right + 24
        sidebar_width = width - sidebar_x - 24
        self.slots = {
            'village-board': pygame.Rect(sidebar_x, 128, sidebar_width, 96),
            'lobby-banner': pygame.Rect(sidebar_x, 236, sidebar_width, 96),
        }
        self.controls = {
            'username': pygame.Rect(40, 167, width - 80, 44),
            'password': pygame.Rect(40, 246, width - 80, 44),
            'login': pygame.Rect(40, 316, 180, 44),
            'up': pygame.Rect(sidebar_x + 86, 346, 76, 40),
            'left': pygame.Rect(sidebar_x, 394, 76, 40),
            'down': pygame.Rect(sidebar_x + 86, 394, 76, 40),
            'right': pygame.Rect(sidebar_x + 172, 394, 76, 40),
            'refresh': pygame.Rect(sidebar_x, 442, 57, 40),
            'logout': pygame.Rect(sidebar_x + 63, 442, 57, 40),
            'gather': pygame.Rect(sidebar_x + 126, 442, 57, 40),
            'train': pygame.Rect(sidebar_x + 189, 442, 59, 40),
            'delivery': pygame.Rect(sidebar_x + 130, 136, 106, 30),
            'analytics': pygame.Rect(sidebar_x, 492, (sidebar_width - 8) // 2, 36),
            'history_panel': pygame.Rect(
                sidebar_x + (sidebar_width - 8) // 2 + 8,
                492,
                (sidebar_width - 8) // 2,
                36,
            ),
            'analytics_refresh': pygame.Rect(
                self.map_rect.x + 58,
                self.map_rect.y + 132,
                128,
                32,
            ),
        }
        self.api_panel = pygame.Rect(
            sidebar_x,
            548,
            sidebar_width,
            self.config.window_height - 572,
        )
        api_button_width = (self.api_panel.width - 30) // 2
        self.controls.update({
            'api_player': pygame.Rect(
                self.api_panel.x + 10,
                self.api_panel.y + 30,
                api_button_width,
                26,
            ),
            'api_history': pygame.Rect(
                self.api_panel.x + 20 + api_button_width,
                self.api_panel.y + 30,
                api_button_width,
                26,
            ),
        })

    def text(self, value: Any, pos: Any, color=INK, font=None) -> None:
        self.screen.blit((font or self.font).render(str(value), True, color), pos)

    def wrapped(self, value: Any, x: int, y: int, width: int,
                font=None, color=MUTED) -> int:
        font = font or self.small
        line = ''
        for char in str(value):
            if line and font.size(line + char)[0] > width:
                self.text(line, (x, y), color, font)
                y += font.get_linesize()
                line = ''
            line += char
        self.text(line, (x, y), color, font)
        return y + font.get_linesize()

    def button(self, name: str, label: str, disabled: bool = False, color=None) -> None:
        rect = self.controls[name]
        fill = (52, 68, 77) if disabled else (color or ACCENT)
        pygame.draw.rect(self.screen, fill, rect, border_radius=7)
        rendered = self.small.render(label, True, MUTED if disabled else BG)
        self.screen.blit(rendered, rendered.get_rect(center=rect.center))

    def draw_slot(self, name: str) -> None:
        pygame.draw.rect(self.screen, CARD, self.slots[name], border_radius=10)

    def draw_tile(self, name: str, x: int, y: int, fallback) -> pygame.Rect:
        rect = pygame.Rect(
            self.map_rect.x + x * TILE_SIZE,
            self.map_rect.y + y * TILE_SIZE,
            TILE_SIZE,
            TILE_SIZE,
        )
        image = self.assets.get(name)
        if image is None:
            pygame.draw.rect(self.screen, fallback, rect)
        else:
            self.screen.blit(image, rect)
        return rect

    def draw_sprite_at_tile(self, name: str, x: int, y: int, fallback) -> None:
        tile = pygame.Rect(
            self.map_rect.x + x * TILE_SIZE,
            self.map_rect.y + y * TILE_SIZE,
            TILE_SIZE,
            TILE_SIZE,
        )
        image = self.assets.get(name)
        if image is None:
            pygame.draw.rect(self.screen, fallback, tile.inflate(-8, -5), border_radius=4)
        else:
            target = image.get_rect(midbottom=(tile.centerx, tile.bottom))
            self.screen.blit(image, target)
