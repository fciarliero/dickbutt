"""Un personaje: glande + tronco articulado + dos testículos.

Marco local de cada cuerpo: +x apunta hacia adelante (hacia la cabeza).
"""
from __future__ import annotations

import math

import pymunk
from pymunk import Vec2d

from . import config as C

HALF = C.SEG_LEN / 2
HEAD_OVERLAP = C.HEAD_R * 0.6
# Puntos en el marco local del último segmento (la base)
BALL_REST = [
    Vec2d(-HALF - C.BALL_R * 0.3, side * (C.BALL_R + C.BALL_GAP / 2)) for side in (1, -1)
]
TARGET_LOCAL = Vec2d(-HALF - C.BALL_R * 0.6, 0)  # el hueco entre las bolas: la zona objetivo
COUPLE_LOCAL = Vec2d(-HALF - C.HEAD_R * 0.4, 0)  # donde queda clavada la cabeza del que me conquista


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def _rel_turns(a: pymunk.Body, b: pymunk.Body) -> float:
    """Múltiplo de 2π más cercano a b.angle - a.angle (los ángulos de pymunk no se envuelven)."""
    return 2 * math.pi * round((b.angle - a.angle) / (2 * math.pi))


def add_bend_joints(space: pymunk.Space, a: pymunk.Body, b: pymunk.Body,
                    stiffness: float, damping: float, max_bend: float) -> list:
    rest = _rel_turns(a, b)
    joints = [
        pymunk.DampedRotarySpring(a, b, rest, stiffness, damping),
        pymunk.RotaryLimitJoint(a, b, rest - max_bend, rest + max_bend),
    ]
    space.add(*joints)
    return joints


class Character:
    def __init__(self, space: pymunk.Space, player_id: str, pos: tuple[float, float],
                 angle: float, group: int):
        self.space = space
        self.player_id = player_id
        self.coupling: list = []  # joints que pegan MI cabeza a la base del de adelante
        fwd = Vec2d(1, 0).rotated(angle)
        pos = Vec2d(*pos)

        self.head = self._body(C.HEAD_MASS, pymunk.moment_for_circle(C.HEAD_MASS, 0, C.HEAD_R), pos, angle)
        self.shapes = [pymunk.Circle(self.head, C.HEAD_R)]

        self.segs: list[pymunk.Body] = []
        for i in range(C.SEG_COUNT):
            center = pos - fwd * (HEAD_OVERLAP + C.SEG_LEN * (i + 0.5))
            moment = pymunk.moment_for_segment(C.SEG_MASS, (-HALF, 0), (HALF, 0), C.SEG_R)
            seg = self._body(C.SEG_MASS, moment, center, angle)
            self.shapes.append(pymunk.Segment(seg, (-HALF, 0), (HALF, 0), C.SEG_R))
            self.segs.append(seg)

        self.balls: list[pymunk.Body] = []
        for rest in BALL_REST:
            ball = self._body(C.BALL_MASS, pymunk.moment_for_circle(C.BALL_MASS, 0, C.BALL_R),
                              self.base.local_to_world(rest), angle)
            self.shapes.append(pymunk.Circle(ball, C.BALL_R))
            self.balls.append(ball)

        for s in self.shapes:
            s.friction = 0.5
            s.elasticity = 0.2
        space.add(self.head, *self.segs, *self.balls, *self.shapes)
        self.set_group(group)

        self.joints: list = []
        chain = [self.head, *self.segs]
        for i, (a, b) in enumerate(zip(chain, chain[1:])):
            anchor_a = (-HEAD_OVERLAP, 0) if i == 0 else (-HALF, 0)
            pivot = pymunk.PivotJoint(a, b, anchor_a, (HALF, 0))
            space.add(pivot)
            self.joints.append(pivot)
            self.joints += add_bend_joints(space, a, b, C.SHAFT_STIFFNESS, C.SHAFT_DAMPING, C.SHAFT_MAX_BEND)

        for ball, rest in zip(self.balls, BALL_REST):
            spring = pymunk.DampedSpring(self.base, ball, rest, (0, 0), 0, C.BALL_STIFFNESS, C.BALL_DAMPING)
            slide = pymunk.SlideJoint(self.base, ball, rest, (0, 0), 0, C.BALL_MAX_DIST)
            space.add(spring, slide)
            self.joints += [spring, slide]

    @staticmethod
    def _body(mass, moment, pos, angle) -> pymunk.Body:
        b = pymunk.Body(mass, moment)
        b.position = pos
        b.angle = angle
        return b

    @property
    def base(self) -> pymunk.Body:
        return self.segs[-1]

    @property
    def bodies(self) -> list[pymunk.Body]:
        return [self.head, *self.segs, *self.balls]

    def set_group(self, group: int) -> None:
        for s in self.shapes:
            s.filter = pymunk.ShapeFilter(group=group)

    def forward(self, body: pymunk.Body | None = None) -> Vec2d:
        return Vec2d(1, 0).rotated((body or self.head).angle)

    def target_point(self) -> Vec2d:
        return self.base.local_to_world(TARGET_LOCAL)

    def couple_to(self, front: "Character") -> None:
        """Clava mi cabeza entre los testículos de `front`."""
        pivot = pymunk.PivotJoint(front.base, self.head, COUPLE_LOCAL, (0, 0))
        pivot.max_bias = C.COUPLE_MAX_BIAS
        self.space.add(pivot)
        self.coupling = [pivot, *add_bend_joints(self.space, front.base, self.head,
                                                  C.SHAFT_STIFFNESS * 0.5, C.SHAFT_DAMPING,
                                                  C.COUPLE_MAX_BEND)]

    def remove(self) -> None:
        self.space.remove(*self.coupling, *self.joints, *self.shapes, *self.bodies)
        self.coupling = []

    def snapshot(self) -> dict:
        r = lambda v: round(v, 1)
        return {
            "h": [r(self.head.position.x), r(self.head.position.y), round(self.head.angle, 3)],
            "s": [[r(b.position.x), r(b.position.y), round(b.angle, 3)] for b in self.segs],
            "b": [[r(b.position.x), r(b.position.y)] for b in self.balls],
        }
