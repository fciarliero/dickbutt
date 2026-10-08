"""Una sala sin red: conexiones → jugadores, protocolo JSON y loop de paso fijo.

La usa el host P2P en el navegador (Pyodide, `client/host-worker.js`): el worker le pasa
los mensajes de cada conexión y le da `send(conn, text)` y `kick(conn)` para contestar.
El protocolo es el mismo que el del WebSocket de `main.py` (ARCHITECTURE.md, sección 10).
"""
from __future__ import annotations

import json
from typing import Callable

from . import config as C
from .game import Game

# Lo que el cliente necesita saber del servidor: tamaños y las constantes de la predicción.
CLIENT_CONFIG = {
    "headR": C.HEAD_R, "segR": C.SEG_R, "segLen": C.SEG_LEN, "ballR": C.BALL_R,
    "snapshotHz": C.PHYSICS_HZ / C.BROADCAST_EVERY,
    "boostCooldown": C.BOOST_COOLDOWN, "boostDuration": C.BOOST_DURATION,
    "boostSpeedMult": C.BOOST_SPEED_MULT, "boostThrustMult": C.BOOST_THRUST_MULT,
    "physicsHz": C.PHYSICS_HZ, "substeps": C.SUBSTEPS,
    "turnSpeed": C.TURN_SPEED, "turnBlend": C.TURN_BLEND, "maxSpeed": C.MAX_SPEED,
    "thrust": C.THRUST, "chainThrustBonus": C.CHAIN_THRUST_BONUS, "damping": C.SPACE_DAMPING,
    "charMass": C.HEAD_MASS + C.SEG_COUNT * C.SEG_MASS + 2 * C.BALL_MASS,
}


def dumps(msg: dict) -> str:
    return json.dumps(msg, separators=(",", ":"))


class Room:
    def __init__(self, version: str, send: Callable[[str, str], None], kick: Callable[[str], None]):
        self.game = Game()
        self.version = version
        self.send = send  # send(conn, text): manda a una conexión
        self.kick = kick  # kick(conn): cierra una conexión
        self.conns: dict[str, str] = {}  # conn → id de jugador
        self.next_t: float | None = None

    def receive(self, conn: str, text: str) -> None:
        try:
            msg = json.loads(text)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        kind = msg.get("t")
        pid = self.conns.get(conn)
        if pid is None:
            if kind != "join":
                self.kick(conn)
                return
            try:
                player = self.game.add_player(str(msg.get("name", "")))
            except ValueError as e:
                self.send(conn, dumps({"t": "error", "msg": str(e)}))
                self.kick(conn)
                return
            self.conns[conn] = player.id
            self.send(conn, dumps({"t": "welcome", "id": player.id, "version": self.version,
                                   "arena": self.game.arena, "config": CLIENT_CONFIG}))
        elif kind == "input":
            self.game.set_input(pid, msg.get("l", 0), msg.get("r", 0), msg.get("u", 0), msg.get("b", 0))
        elif kind == "ping":
            self.send(conn, dumps({"t": "pong", "c": msg.get("c")}))
        elif kind == "add_bot":
            try:
                self.game.add_bot()
            except ValueError as e:
                self.send(conn, dumps({"t": "error", "msg": str(e)}))
        elif kind == "remove_bot":
            self.game.remove_bot()

    def leave(self, conn: str) -> None:
        pid = self.conns.pop(conn, None)
        if pid:
            self.game.remove_player(pid)

    def tick(self, now: float) -> str | None:
        """Corre los ticks que se deben hasta `now` (segundos). Devuelve el snapshot si toca mandarlo."""
        dt = 1 / C.PHYSICS_HZ
        if self.next_t is None or now - self.next_t > 0.25:  # muy atrasados: no recuperar todo
            self.next_t = now
        send = False
        while now >= self.next_t:
            self.game.step(dt)
            send |= self.game.tick_n % C.BROADCAST_EVERY == 0
            self.next_t += dt
        if not send:
            return None
        state = self.game.snapshot()
        events = self.game.drain_events()
        if events:
            state["events"] = events
        return dumps(state)
