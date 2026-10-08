"""Estado del juego: física, jugadores, cadenas y fases de ronda. Sin red."""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import pymunk
from pymunk import Vec2d

from . import arena, bots
from . import config as C
from .chains import Chain, merge, on_disconnect, winner
from .character import Character

LOBBY, COUNTDOWN, PLAYING, ROUND_OVER = "lobby", "countdown", "playing", "round_over"


@dataclass(eq=False)
class Player:
    id: str
    name: str
    color: str
    input: dict = field(default_factory=lambda: {"l": 0, "r": 0, "u": 0, "b": 0})
    connected: bool = True
    char: Character | None = None
    chain_id: int | None = None
    bot: bool = False
    brain: dict = field(default_factory=dict)  # estado interno de la IA (solo bots)
    boost_until: int = 0  # tick hasta el que dura el boost
    boost_ready: int = 0  # tick desde el que se puede volver a usar


class Game:
    def __init__(self):
        self.players: dict[str, Player] = {}
        self.chains: dict[int, Chain] = {}
        self.phase = LOBBY
        self.timer = 0.0
        self.tick_n = 0
        self.winner: str | None = None
        self.events: list[dict] = []
        self._ids = itertools.count(1)
        self._new_space()

    # ------------------------------------------------------------ jugadores
    def add_player(self, name: str, bot: bool = False) -> Player:
        if sum(p.connected for p in self.players.values()) >= C.MAX_PLAYERS:
            raise ValueError("la sala está llena")
        used = {p.color for p in self.players.values()}
        color = next((c for c in C.COLORS if c not in used), C.COLORS[len(self.players) % len(C.COLORS)])
        name = (name or "").strip()[: C.NAME_MAX] or "anónimo"
        p = Player(f"p{next(self._ids)}", name, color, bot=bot)
        self.players[p.id] = p
        self.events.append({"kind": "join", "who": p.id})
        if self.phase == COUNTDOWN:
            self._spawn_all()  # que entre a la ronda que está por empezar
        return p

    def remove_player(self, pid: str) -> None:
        p = self.players.get(pid)
        if not p:
            return
        p.connected = False
        self.events.append({"kind": "leave", "who": pid})
        chain = self.chains.get(p.chain_id) if p.chain_id is not None else None
        if p.char is None or chain is None or len(chain.members) == 1 or self.phase in (LOBBY, COUNTDOWN):
            if p.char:
                p.char.remove()
            if chain:
                self.chains.pop(chain.id)
            del self.players[pid]
            if self.phase == COUNTDOWN:
                self._spawn_all()
        else:
            # queda como vagón pasivo; si piloteaba, el control pasa a otro
            on_disconnect(chain, pid, self._participants())

    def add_bot(self) -> Player:
        taken = {p.name for p in self.players.values()}
        name = next((n for n in bots.NAMES if n not in taken), f"Bot {len(self.players) + 1}")
        return self.add_player(name, bot=True)

    def remove_bot(self) -> None:
        live = [p for p in self.players.values() if p.bot and p.connected]
        if live:
            self.remove_player(live[-1].id)

    def _humans(self) -> int:
        return sum(p.connected and not p.bot for p in self.players.values())

    def set_input(self, pid: str, l: int, r: int, u: int, b: int = 0) -> None:
        p = self.players.get(pid)
        if p:
            if b and not p.input.get("b"):
                self.try_boost(p)
            p.input = {"l": int(bool(l)), "r": int(bool(r)), "u": int(bool(u)), "b": int(bool(b))}

    def try_boost(self, p: Player) -> bool:
        if self.phase not in (PLAYING, ROUND_OVER) or not p.char or self.tick_n < p.boost_ready:
            return False
        p.boost_until = self.tick_n + round(C.BOOST_DURATION * C.PHYSICS_HZ)
        p.boost_ready = self.tick_n + round(C.BOOST_COOLDOWN * C.PHYSICS_HZ)
        return True

    def boosting(self, p: Player) -> bool:
        return self.tick_n < p.boost_until

    def _participants(self) -> set[str]:
        return {p.id for p in self.players.values() if p.connected and p.char}

    # --------------------------------------------------------------- rondas
    def _new_space(self) -> None:
        self.space = pymunk.Space()
        self.space.damping = C.SPACE_DAMPING
        self.space.iterations = 20
        self.arena = arena.build(self.space)

    def _spawn_all(self) -> None:
        self._new_space()
        self.chains = {}
        active = [p for p in self.players.values() if p.connected]
        n = len(active)
        cx, cy = C.ARENA_W / 2, C.ARENA_H / 2
        for i, p in enumerate(active):
            t = 2 * math.pi * i / max(n, 1)
            pos = (cx + C.SPAWN_RX * math.cos(t), cy + C.SPAWN_RY * math.sin(t))
            facing = math.atan2(cy - pos[1], cx - pos[0])
            cid = i + 1
            p.char = Character(self.space, p.id, pos, facing, group=cid)
            p.chain_id = cid
            self.chains[cid] = Chain(cid, [p.id], p.id)

    def _reset(self) -> None:
        for pid in [pid for pid, p in self.players.items() if not p.connected]:
            del self.players[pid]
        for p in self.players.values():
            p.char = None
            p.chain_id = None
        self.chains = {}
        self.winner = None
        self._new_space()
        self.phase = LOBBY

    def _update_phase(self, dt: float) -> None:
        connected = sum(p.connected for p in self.players.values())
        if self.phase != LOBBY and self.phase != ROUND_OVER and not self._humans():
            self._reset()  # sin humanos los bots no juegan solos
        elif self.phase == LOBBY:
            if connected >= C.MIN_PLAYERS and self._humans():
                self.phase, self.timer = COUNTDOWN, C.COUNTDOWN_S
                self._spawn_all()
        elif self.phase == COUNTDOWN:
            self.timer -= dt
            if connected < C.MIN_PLAYERS:
                self._reset()
            elif self.timer <= 0:
                self.phase = PLAYING
        elif self.phase == PLAYING:
            if not self._participants():
                self._reset()
        elif self.phase == ROUND_OVER:
            self.timer -= dt
            if self.timer <= 0:
                self._reset()

    # --------------------------------------------------------------- física
    def step(self, dt: float) -> None:
        self.tick_n += 1
        self._update_phase(dt)
        controls = self.phase in (PLAYING, ROUND_OVER)
        if controls:
            bots.think(self)
        sub = dt / C.SUBSTEPS
        for _ in range(C.SUBSTEPS):
            if controls:
                self._apply_controls()  # las fuerzas se resetean en cada space.step
            self.space.step(sub)
        self._clamp_speeds()
        if self.phase == PLAYING:
            self._check_penetrations()
            self._check_winner()

    def _apply_controls(self) -> None:
        for chain in self.chains.values():
            if chain.pilot is not None:
                inp = self.players[chain.pilot].input
                head = self.players[chain.front].char.head
                turn = inp["r"] - inp["l"]
                if turn:
                    target = turn * C.TURN_SPEED
                    head.angular_velocity += (target - head.angular_velocity) * C.TURN_BLEND
                else:
                    head.angular_velocity *= 0.9
                thrust = C.THRUST * (1 + C.CHAIN_THRUST_BONUS * (len(chain.members) - 1))
                max_speed = C.MAX_SPEED
                if self.boosting(self.players[chain.pilot]):
                    # el boost empuja aunque no aprietes ↑
                    head.apply_force_at_local_point((thrust * C.BOOST_THRUST_MULT, 0), (0, 0))
                    max_speed *= C.BOOST_SPEED_MULT
                elif inp["u"]:
                    head.apply_force_at_local_point((thrust, 0), (0, 0))
                speed = head.velocity.length
                if speed > max_speed:
                    soft = max_speed + (speed - max_speed) * C.OVERSPEED_DECAY
                    head.velocity = head.velocity.scale_to_length(soft)
            for pid in chain.members:
                p = self.players[pid]
                if pid == chain.pilot or not p.connected:
                    continue
                inp = p.input
                head = p.char.head
                fwd = Vec2d(1, 0).rotated(head.angle)
                push = fwd * inp["u"] + fwd.perpendicular() * (inp["r"] - inp["l"])
                force = C.THRUST * C.SABOTAGE_FACTOR
                if self.boosting(p):
                    push = push if push.length else fwd
                    force *= C.BOOST_SABOTAGE_MULT
                if push.length:
                    head.apply_force_at_world_point(push.normalized() * force, head.position)

    def _clamp_speeds(self) -> None:
        for p in self.players.values():
            if p.char:
                for b in p.char.bodies:
                    if b.velocity.length > C.SAFETY_SPEED:
                        b.velocity = b.velocity.scale_to_length(C.SAFETY_SPEED)

    def _check_penetrations(self) -> None:
        hits = []
        for x in self.chains.values():
            if x.pilot is None:
                continue
            head = self.players[x.front].char.head
            fwd = Vec2d(1, 0).rotated(head.angle)
            for y in self.chains.values():
                if y.id == x.id:
                    continue
                victim = self.players[y.last].char
                if head.position.get_distance(victim.target_point()) > C.ENTRY_RADIUS:
                    continue
                vfwd = victim.forward(victim.base)
                if abs(fwd.get_angle_between(vfwd)) > C.ENTRY_ANGLE:
                    continue
                if (head.velocity - victim.base.velocity).dot(vfwd) < C.ENTRY_MIN_SPEED:
                    continue
                hits.append((x.id, y.id))
        used: set[int] = set()
        for xid, yid in hits:
            if xid in used or yid in used:
                continue
            used |= {xid, yid}
            self._couple(self.chains[xid], self.chains[yid])

    def _couple(self, attacker: Chain, target: Chain) -> None:
        self.players[attacker.front].char.couple_to(self.players[target.last].char)
        new = merge(target, attacker)
        del self.chains[attacker.id]
        self.chains[new.id] = new
        for pid in attacker.members:
            p = self.players[pid]
            p.chain_id = new.id
            p.char.set_group(new.id)
        self.events.append({"kind": "conquest", "by": attacker.pilot,
                            "entered": target.last, "controls": target.front})

    def _check_winner(self) -> None:
        w = winner(list(self.chains.values()), self._participants())
        if w:
            self.phase, self.timer, self.winner = ROUND_OVER, C.ROUND_OVER_S, w.pilot
            self.events.append({"kind": "win", "who": w.pilot, "size": len(w.members)})

    # ------------------------------------------------------------- snapshot
    def snapshot(self) -> dict:
        lasts = {c.last for c in self.chains.values()}
        chars = {}
        for p in self.players.values():
            if p.char:
                s = p.char.snapshot()
                if p.id in lasts:
                    tp = p.char.target_point()
                    s["t"] = [round(tp.x, 1), round(tp.y, 1)]
                chars[p.id] = s
        return {
            "t": "state",
            "tick": self.tick_n,
            "phase": self.phase,
            "timer": round(max(self.timer, 0), 2),
            "winner": self.winner,
            "players": [{"id": p.id, "name": p.name, "color": p.color, "connected": p.connected, "bot": p.bot,
                         "boost": round(max(0, p.boost_ready - self.tick_n) / C.PHYSICS_HZ, 2),
                         "boosting": self.boosting(p),
                         "chain": p.chain_id,
                         "spectator": p.char is None and self.phase in (PLAYING, ROUND_OVER)}
                        for p in self.players.values()],
            "chains": [{"id": c.id, "members": c.members, "pilot": c.pilot} for c in self.chains.values()],
            "chars": chars,
        }

    def drain_events(self) -> list[dict]:
        ev, self.events = self.events, []
        return ev
