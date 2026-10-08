import pymunk

from . import config as C


def build(space: pymunk.Space) -> dict:
    """Agrega paredes y obstáculos estáticos. Devuelve su geometría para el cliente."""
    w, h = C.ARENA_W, C.ARENA_H
    corners = [(0, 0), (w, 0), (w, h), (0, h)]
    walls = []
    for i in range(4):
        a, b = corners[i], corners[(i + 1) % 4]
        seg = pymunk.Segment(space.static_body, a, b, C.WALL_RADIUS)
        seg.elasticity = 0.4
        seg.friction = 0.4
        space.add(seg)
        walls.append([*a, *b])

    obstacles = []
    for x, y, r in C.OBSTACLES:
        circle = pymunk.Circle(space.static_body, r, (x, y))
        circle.elasticity = 0.5
        circle.friction = 0.4
        space.add(circle)
        obstacles.append([x, y, r])

    return {"w": w, "h": h, "walls": walls, "obstacles": obstacles}
