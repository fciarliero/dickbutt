import json

from server import config as C
from server.game import COUNTDOWN
from server.room import Room


def make_room():
    sent, kicked = [], []
    room = Room("v1", lambda conn, text: sent.append((conn, json.loads(text))), kicked.append)
    return room, sent, kicked


def test_join_manda_welcome():
    room, sent, _ = make_room()
    room.receive("a", json.dumps({"t": "join", "name": "Ana"}))
    conn, msg = sent[-1]
    assert conn == "a" and msg["t"] == "welcome" and msg["version"] == "v1"
    assert msg["config"]["maxSpeed"] == C.MAX_SPEED
    assert room.game.players[msg["id"]].name == "Ana"


def test_primer_mensaje_que_no_es_join_cierra():
    room, sent, kicked = make_room()
    room.receive("a", json.dumps({"t": "input", "u": 1}))
    assert kicked == ["a"] and not sent and not room.game.players


def test_basura_se_ignora():
    room, sent, kicked = make_room()
    room.receive("a", "no es json")
    room.receive("a", "[1, 2]")
    assert not sent and not kicked


def test_sala_llena():
    room, sent, kicked = make_room()
    for i in range(C.MAX_PLAYERS):
        room.receive(f"c{i}", json.dumps({"t": "join", "name": f"j{i}"}))
    room.receive("x", json.dumps({"t": "join", "name": "tarde"}))
    assert sent[-1] == ("x", {"t": "error", "msg": "la sala está llena"})
    assert kicked == ["x"]


def test_input_ping_y_bots():
    room, sent, _ = make_room()
    room.receive("a", json.dumps({"t": "join", "name": "Ana"}))
    pid = sent[-1][1]["id"]
    room.receive("a", json.dumps({"t": "input", "l": 1, "r": 0, "u": 1, "b": 0}))
    assert room.game.players[pid].input == {"l": 1, "r": 0, "u": 1, "b": 0}
    room.receive("a", json.dumps({"t": "ping", "c": 123.5}))
    assert sent[-1] == ("a", {"t": "pong", "c": 123.5})
    room.receive("a", json.dumps({"t": "add_bot"}))
    assert sum(p.bot for p in room.game.players.values()) == 1
    room.receive("a", json.dumps({"t": "remove_bot"}))
    assert sum(p.bot for p in room.game.players.values()) == 0


def test_leave_saca_al_jugador():
    room, _, _ = make_room()
    room.receive("a", json.dumps({"t": "join", "name": "Ana"}))
    room.leave("a")
    room.leave("a")  # dos veces no rompe
    assert not room.game.players


def test_tick_paso_fijo_y_snapshot():
    room, _, _ = make_room()
    room.receive("a", json.dumps({"t": "join", "name": "Ana"}))
    room.receive("a", json.dumps({"t": "add_bot"}))
    t = 100.0
    states = []
    for _ in range(60):  # 1 s en pasos de 1/60
        s = room.tick(t)
        if s:
            states.append(json.loads(s))
        t += 1 / C.PHYSICS_HZ
    assert room.game.tick_n == 60
    assert len(states) == 60 // C.BROADCAST_EVERY
    assert states[0]["events"][0]["kind"] == "join"
    assert states[-1]["phase"] == COUNTDOWN and len(states[-1]["chars"]) == 2


def test_tick_no_recupera_atrasos_largos():
    room, _, _ = make_room()
    room.tick(0.0)
    room.tick(10.0)  # p. ej. la pestaña estuvo suspendida
    assert room.game.tick_n == 2
