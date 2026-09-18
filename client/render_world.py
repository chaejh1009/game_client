"""Village map and player drawing for the pygame client."""
import pygame

from ports import StatePort
from render_support import (
    ACCENT,
    GRASS_FALLBACK,
    MAP_COLUMNS,
    MAP_ROWS,
    PATH_FALLBACK,
    PENDING,
    TILE_SIZE,
    TRAIN,
    RenderSupport,
)


def draw_world(view: RenderSupport, state: StatePort) -> None:
    """Draw terrain, landmarks, decorations, and versioned player positions."""
    old_clip = view.screen.get_clip()
    view.screen.set_clip(view.map_rect)
    path_tiles = (
        {(x, 2) for x in range(MAP_COLUMNS)}
        | {(2, y) for y in range(MAP_ROWS)}
    )
    for y in range(MAP_ROWS):
        for x in range(MAP_COLUMNS):
            name = 'path' if (x, y) in path_tiles else 'grass'
            fallback = PATH_FALLBACK if name == 'path' else GRASS_FALLBACK
            view.draw_tile(name, x, y, fallback)

    gather = pygame.Rect(
        view.map_rect.x + 2 * TILE_SIZE,
        view.map_rect.y + 2 * TILE_SIZE,
        TILE_SIZE,
        TILE_SIZE,
    )
    pygame.draw.rect(view.screen, PENDING, gather, width=2)

    train = pygame.Rect(
        view.map_rect.x + 3 * TILE_SIZE,
        view.map_rect.y + 2 * TILE_SIZE,
        TILE_SIZE,
        TILE_SIZE,
    )
    pygame.draw.rect(view.screen, TRAIN, train, width=2)
    pygame.draw.line(
        view.screen,
        TRAIN,
        (train.centerx, train.y + 15),
        (train.centerx, train.bottom - 5),
        2,
    )
    sign = pygame.Rect(train.x + 6, train.y + 6, TILE_SIZE - 12, 11)
    pygame.draw.rect(view.screen, (31, 58, 91), sign, border_radius=2)
    pygame.draw.rect(view.screen, TRAIN, sign, width=1, border_radius=2)

    # Decorations never alter movement or the server's collision rules.
    for x, y in ((5, 4), (12, 3), (16, 10), (8, 12)):
        view.draw_sprite_at_tile('tree', x, y, (35, 104, 60))
    for x, y in ((7, 6), (14, 8)):
        view.draw_sprite_at_tile('house', x, y, (156, 91, 69))

    own_id = state.my_player_id
    players = sorted(
        state.players.values(),
        key=lambda item: item['player_id'] == own_id,
    )
    for player in players:
        is_own = player['player_id'] == own_id
        fallback = (76, 106, 190) if is_own else (214, 116, 86)
        view.draw_sprite_at_tile('hero', player['x'], player['y'], fallback)
        tile_x = view.map_rect.x + player['x'] * TILE_SIZE
        tile_y = view.map_rect.y + player['y'] * TILE_SIZE
        marker = ACCENT if is_own else PENDING
        outline = pygame.Rect(tile_x + 2, tile_y + 2, TILE_SIZE - 4, TILE_SIZE - 4)
        pygame.draw.rect(
            view.screen,
            marker,
            outline,
            width=3 if is_own else 1,
            border_radius=5,
        )
        pygame.draw.circle(
            view.screen,
            marker,
            (tile_x + TILE_SIZE - 5, tile_y + 5),
            4,
        )
        label = view.small.render(str(player['player_id']), True, marker)
        view.screen.blit(label, (tile_x + 2, tile_y + 1))
    pygame.draw.rect(view.screen, (10, 18, 24), view.map_rect, width=2)
    view.screen.set_clip(old_clip)
