"""Servidor web: sirve el cliente y corre el loop del juego."""
from __future__ import annotations

import asyncio
import atexit
import contextlib
import ctypes
import functools
import gc
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import config as C
from .game import Game

CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"


def _client_version() -> str:
    """Huella de los archivos del cliente: cambia con cualquier edición."""
    h = hashlib.sha1()
    for f in sorted(CLIENT_DIR.rglob("*")):
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:10]


# Se calcula al arrancar. Si un navegador trae otra versión (pestaña abierta durante
# un reinicio, caché vieja), el cliente se recarga solo al conectarse.
CLIENT_VERSION = _client_version()

game = Game()
sockets: dict[str, WebSocket] = {}


@atexit.register
def _free_physics() -> None:
    # pymunk se desmonta antes que este módulo al salir; liberar el Space antes evita un segfault
    game.players.clear()
    game.chains.clear()
    game.space = None
    gc.collect()

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

# Lag simulado para probar la predicción en local: SIM_LAG_MS=150 python run.py
# (es el ping total; se reparte mitad a la ida y mitad a la vuelta)
SIM_LAG = float(os.environ.get("SIM_LAG_MS", 0)) / 1000 / 2


def _ignore_result(task: asyncio.Task) -> None:
    if not task.cancelled():
        task.exception()  # la desconexión la maneja el handler del socket


def later(fn) -> None:
    """Corre fn ahora o, con lag simulado, más tarde (respetando el orden)."""
    if SIM_LAG:
        asyncio.get_running_loop().call_later(SIM_LAG, fn)
    else:
        fn()


async def send(ws: WebSocket, text: str) -> None:
    if SIM_LAG:
        later(lambda: asyncio.ensure_future(ws.send_text(text)).add_done_callback(_ignore_result))
    else:
        await ws.send_text(text)


async def broadcast(text: str) -> None:
    if not sockets:
        return
    # los errores se ignoran: el handler de cada socket se encarga de la desconexión
    await asyncio.gather(*(send(ws, text) for ws in list(sockets.values())),
                         return_exceptions=True)


async def game_loop() -> None:
    dt = 1 / C.PHYSICS_HZ
    next_t = time.perf_counter()
    while True:
        now = time.perf_counter()
        if now - next_t > 0.25:  # nos atrasamos mucho (p. ej. suspensión): no recuperar todo
            next_t = now
        send = False
        while now >= next_t:
            game.step(dt)
            send |= game.tick_n % C.BROADCAST_EVERY == 0
            next_t += dt
        if send:
            state = game.snapshot()
            events = game.drain_events()
            if events:
                state["events"] = events
            await broadcast(json.dumps(state, separators=(",", ":")))
        await asyncio.sleep(max(0.0, next_t - time.perf_counter()))


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    # Windows despierta los sleeps cada ~15,6 ms por defecto: pedir 1 ms para que los ticks salgan parejos
    windows = sys.platform == "win32"
    if windows:
        ctypes.windll.winmm.timeBeginPeriod(1)
    task = asyncio.create_task(game_loop())
    try:
        yield
    finally:
        task.cancel()
        if windows:
            ctypes.windll.winmm.timeEndPeriod(1)


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=CLIENT_DIR), name="static")


@app.middleware("http")
async def no_stale_client(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"  # el navegador siempre revalida: nunca usa un JS viejo
    return response


@app.get("/")
async def index():
    html = (CLIENT_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace('src="/static/game.js"', f'src="/static/game.js?v={CLIENT_VERSION}"')
    html = html.replace("<head>", f'<head>\n<meta name="client-version" content="{CLIENT_VERSION}">', 1)
    return HTMLResponse(html)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    player = None
    try:
        msg = await ws.receive_json()
        if msg.get("t") != "join":
            await ws.close(code=1008)
            return
        try:
            player = game.add_player(str(msg.get("name", "")))
        except ValueError as e:
            await ws.send_json({"t": "error", "msg": str(e)})
            await ws.close()
            return
        sockets[player.id] = ws
        await ws.send_json({"t": "welcome", "id": player.id, "version": CLIENT_VERSION,
                            "arena": game.arena, "config": CLIENT_CONFIG})
        while True:
            msg = await ws.receive_json()
            kind = msg.get("t")
            if kind == "input":
                later(functools.partial(game.set_input, player.id, msg.get("l", 0), msg.get("r", 0),
                                        msg.get("u", 0), msg.get("b", 0)))
            elif kind == "ping":
                pong = json.dumps({"t": "pong", "c": msg.get("c")})
                later(lambda: asyncio.ensure_future(send(ws, pong)).add_done_callback(_ignore_result))
            elif kind == "add_bot":
                try:
                    game.add_bot()
                except ValueError as e:
                    await ws.send_json({"t": "error", "msg": str(e)})
            elif kind == "remove_bot":
                game.remove_bot()
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        if player:
            sockets.pop(player.id, None)
            game.remove_player(player.id)
