"""IA de los bots: deciden qué teclas apretar, igual que un jugador humano.

- Si pilotean: eligen la cola libre más cercana, se ubican detrás de ella y
  entran alineados. Esquivan paredes y obstáculos mirando hacia adelante.
- Si están conquistados: sabotean tironeando para los costados.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from pymunk import Vec2d

from . import config as C
from .character import wrap_angle

if TYPE_CHECKING:
    from .game import Game, Player

NAMES = ["🤖 Pepe", "🤖 Tito", "🤖 Coco", "🤖 Lalo", "🤖 Nacho", "🤖 Rulo", "🤖 Beto", "🤖 Chicho"]

APPROACH_DIST = 130  # a qué distancia detrás de la cola se ubica antes de entrar
LOOKAHEAD = (60, 120)
WALL_MARGIN = 60
OBSTACLE_MARGIN = 45
APPROACH_MARGIN = 45  # el punto de aproximación nunca queda pegado a la pared
PATIENCE_S = 5  # segundos sin acercarse a la presa antes de fintar y cambiar
REACTION_TICKS = 4  # cada cuántos ticks re-decide (los humanos tampoco son instantáneos)
BOOST_RANGE = 220  # a esta distancia de la cola, alineado, usa el boost
SABOTAGE_BOOST_CHANCE = 0.03  # por decisión, si está conquistado


def think(game: "Game") -> None:
    for p in game.players.values():
        if not (p.bot and p.connected and p.char):
            continue
        if game.tick_n % REACTION_TICKS != hash(p.id) % REACTION_TICKS:
            continue
        chain = game.chains.get(p.chain_id)
        if chain is None:
            continue
        if chain.pilot == p.id:
            p.input = _pilot(game, p, chain)
        else:
            p.input = _sabotage(game, p)
            if random.random() < SABOTAGE_BOOST_CHANCE:
                game.try_boost(p)


def _sabotage(game: "Game", p: "Player") -> dict:
    b = p.brain
    if game.tick_n >= b.get("tug_until", 0):
        b["tug"] = random.choice((-1, 1))
        b["tug_until"] = game.tick_n + random.randint(15, 50)
    return {"l": int(b["tug"] < 0), "r": int(b["tug"] > 0), "u": int(random.random() < 0.5)}


def _pilot(game: "Game", p: "Player", chain) -> dict:
    b = p.brain
    if game.tick_n < b.get("feint_until", 0):
        return b["feint"]

    head = game.players[chain.front].char.head
    pos, ang = head.position, head.angle
    aim, target, final = _aim_point(game, p, chain, pos)

    # paciencia: si no se acerca a la presa en un rato, finta y cambia de presa
    if target is not None:
        d = pos.get_distance(game.players[target].char.target_point())
        if b.get("target") != target or d < b.get("best", math.inf) - 40:
            b.update(target=target, best=d, since=game.tick_n)
        elif game.tick_n - b["since"] > PATIENCE_S * C.PHYSICS_HZ:
            b["feint"] = {"l": int(random.random() < 0.5), "r": 0, "u": int(random.random() < 0.3)}
            b["feint"]["r"] = 1 - b["feint"]["l"]
            b["feint_until"] = game.tick_n + random.randint(30, 80)
            b["ignore"] = target
            b["ignore_until"] = game.tick_n + 5 * C.PHYSICS_HZ
            b.pop("target")
            return b["feint"]

    avoid = None if final else _avoidance(game, pos, ang, aim)
    if avoid is not None:
        desired = avoid
    elif aim is not None:
        desired = (aim - pos).angle
    else:
        if random.random() < 0.05:
            b["wander"] = random.uniform(-0.8, 0.8)
        desired = ang + b.get("wander", 0.0)

    diff = wrap_angle(desired - ang)
    dead = 0.12
    if final and abs(diff) < 0.25 and pos.get_distance(aim) < BOOST_RANGE:
        game.try_boost(p)  # estocada final
    return {
        "l": int(diff < -dead),
        "r": int(diff > dead),
        "u": int(abs(diff) < 1.3 or avoid is not None),
    }


def _clamp(v: Vec2d) -> Vec2d:
    m = APPROACH_MARGIN
    return Vec2d(min(max(v.x, m), C.ARENA_W - m), min(max(v.y, m), C.ARENA_H - m))


def _aim_point(game: "Game", p: "Player", chain, pos: Vec2d):
    """(punto al que apuntar, jugador presa, ¿entrada final?)."""
    b = p.brain
    ignored = b.get("ignore") if game.tick_n < b.get("ignore_until", 0) else None
    candidates = [o for o in game.chains.values() if o.id != chain.id]
    if len(candidates) > 1:
        candidates = [o for o in candidates if o.last != ignored] or candidates
    def cost(o):
        victim = game.players[o.last].char
        # preferir presas cercanas y lentas (las rápidas se escapan)
        return pos.get_distance(victim.target_point()) * (1 + victim.base.velocity.length / 350)

    best = min(candidates, key=cost, default=None)
    if best is None:
        return None, None, False

    victim = game.players[best.last].char
    tp = victim.target_point()
    vf = victim.forward(victim.base)
    side = vf.perpendicular()
    lead = victim.base.velocity * 0.25  # anticipa un poco el movimiento de la víctima
    rel = pos - tp
    lx, ly = rel.dot(vf), rel.dot(side)

    if lx < -15 and abs(ly) < 20 + (-lx) * 0.35:
        return tp + lead, best.last, True  # ya está atrás y dentro del cono: a fondo
    # curva de persecución: cuanto más cerca, más se mete por detrás para llegar alineado
    behind = tp - vf * min(APPROACH_DIST, 0.6 * rel.length)
    if lx > -40:
        # está al costado o adelante: rodear por el lado donde ya está
        behind += side * math.copysign(90, ly or 1)
    return _clamp(behind + lead), best.last, False


def _avoidance(game: "Game", pos: Vec2d, ang: float, aim: Vec2d | None) -> float | None:
    """Si hay una pared u obstáculo adelante, devuelve un ángulo para esquivarlo."""
    fwd = Vec2d(1, 0).rotated(ang)
    reach = pos.get_distance(aim) if aim is not None else math.inf
    for dist in LOOKAHEAD:
        if dist > reach:
            break  # el objetivo está más cerca que el obstáculo
        probe = pos + fwd * dist
        if not (WALL_MARGIN < probe.x < C.ARENA_W - WALL_MARGIN and WALL_MARGIN < probe.y < C.ARENA_H - WALL_MARGIN):
            center = Vec2d(C.ARENA_W / 2, C.ARENA_H / 2)
            return (center - pos).angle
        for x, y, r in C.OBSTACLES:
            c = Vec2d(x, y)
            if probe.get_distance(c) < r + OBSTACLE_MARGIN:
                # cross > 0: el obstáculo queda a la derecha (y crece hacia abajo) → girar a la izquierda
                return ang - 1.0 if fwd.cross(c - pos) > 0 else ang + 1.0
    return None
