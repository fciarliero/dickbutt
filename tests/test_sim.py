import math

import pytest

from server import config as C
from server.character import Character
from server.chains import Chain
from server.game import COUNTDOWN, LOBBY, PLAYING, ROUND_OVER, Game

DT = 1 / C.PHYSICS_HZ
Y = 280  # fila libre de obstáculos


def run(game, seconds):
    for _ in range(int(seconds * C.PHYSICS_HZ)):
        game.step(DT)


def started_game(n=2):
    g = Game()
    players = [g.add_player(name) for name in "ABCDEFGH"[:n]]
    run(g, C.COUNTDOWN_S + 0.1)
    assert g.phase == PLAYING
    return g, players


def place(game, layout):
    """Reubica personajes a mano: layout = {player: (x, y, angulo)}."""
    game._new_space()
    game.chains = {}
    for cid, (p, (x, y, ang)) in enumerate(layout.items(), start=1):
        p.char = Character(game.space, p.id, (x, y), ang, group=cid)
        p.chain_id = cid
        game.chains[cid] = Chain(cid, [p.id], p.id)


def all_finite(game):
    return all(math.isfinite(v) for p in game.players.values() if p.char
               for b in p.char.bodies for v in (*b.position, *b.velocity))


def test_ronda_arranca_con_dos():
    g = Game()
    g.add_player("A")
    g.step(DT)
    assert g.phase == LOBBY
    g.add_player("B")
    g.step(DT)
    assert g.phase == COUNTDOWN


def test_estable_sin_input():
    g, _ = started_game(4)
    run(g, 5)
    assert all_finite(g)
    for p in g.players.values():
        for b in p.char.bodies:
            assert 0 <= b.position.x <= C.ARENA_W and 0 <= b.position.y <= C.ARENA_H


def test_estable_manejando_contra_paredes():
    g, (a, b) = started_game(2)
    g.set_input(a.id, 0, 1, 1)
    g.set_input(b.id, 1, 0, 1)
    run(g, 8)
    assert all_finite(g)


def test_penetracion_desde_atras():
    g, (a, b) = started_game(2)
    place(g, {b: (1300, Y, 0), a: (1100, Y, 0)})
    g.set_input(a.id, 0, 0, 1)
    run(g, 1.5)
    assert len(g.chains) == 1
    chain = next(iter(g.chains.values()))
    assert chain.members == [b.id, a.id]
    assert chain.pilot == a.id
    assert g.phase == ROUND_OVER and g.winner == a.id
    # la cabeza de A queda pegada entre las bolas de B
    run(g, 1)
    assert a.char.head.position.get_distance(b.char.target_point()) < C.ENTRY_RADIUS


def test_desde_el_costado_no_entra():
    g, (a, b) = started_game(2)
    place(g, {b: (1300, Y, 0), a: (1060, Y - 130, math.pi / 2)})  # A baja en perpendicular
    g.set_input(a.id, 0, 0, 1)
    run(g, 1.5)
    assert len(g.chains) == 2


def test_sin_velocidad_no_entra():
    g, (a, b) = started_game(2)
    place(g, {b: (1300, Y, 0), a: (1145, Y, 0)})  # alineado y pegado, pero quieto
    run(g, 1)
    assert len(g.chains) == 2


def test_tercero_toma_la_cadena_y_el_piloto_controla_el_frente():
    g, (a, b, c) = started_game(3)
    place(g, {b: (1400, Y, 0), a: (1210, Y, 0), c: (700, Y, 0)})
    g.set_input(a.id, 0, 0, 1)
    run(g, 0.8)
    assert [ch.members for ch in g.chains.values()] in ([[b.id, a.id], [c.id]], [[c.id], [b.id, a.id]])
    g.set_input(a.id, 0, 0, 0)
    g.set_input(c.id, 0, 0, 1)
    run(g, 4)
    assert g.phase == ROUND_OVER
    chain = next(iter(g.chains.values()))
    assert chain.members == [b.id, a.id, c.id] and chain.pilot == c.id


def test_piloto_se_desconecta():
    g, (a, b, c) = started_game(3)
    place(g, {b: (1300, Y, 0), a: (1100, Y, 0), c: (300, 1300, 0)})
    g.set_input(a.id, 0, 0, 1)
    run(g, 1.5)
    chain = g.chains[b.chain_id]
    assert chain.pilot == a.id
    g.remove_player(a.id)
    assert chain.pilot == b.id
    assert a.id in g.players  # su cuerpo sigue como vagón


def test_reinicio_tras_victoria():
    g, (a, b) = started_game(2)
    place(g, {b: (1300, Y, 0), a: (1100, Y, 0)})
    g.set_input(a.id, 0, 0, 1)
    run(g, 1.5)
    assert g.phase == ROUND_OVER
    run(g, C.ROUND_OVER_S + 0.1)
    assert g.phase == COUNTDOWN
    assert len(g.chains) == 2


def test_espectador_si_entra_tarde():
    g, _ = started_game(2)
    late = g.add_player("tarde")
    assert late.char is None
    g.remove_player(late.id)
    assert late.id not in g.players


@pytest.mark.parametrize("offset", [-20, 12, 20])
def test_entra_con_algo_de_desalineacion(offset):
    g, (a, b) = started_game(2)
    place(g, {b: (1300, Y, 0), a: (1100, Y + offset, 0)})
    g.set_input(a.id, 0, 0, 1)
    run(g, 1.5)
    assert len(g.chains) == 1


def test_boost_acelera_y_tiene_cooldown():
    g, (a, b) = started_game(2)
    place(g, {a: (300, 1300, 0), b: (2000, 300, math.pi)})
    g.set_input(a.id, 0, 0, 1)
    run(g, 2)
    crucero = a.char.head.velocity.length
    g.set_input(a.id, 0, 0, 1, 1)
    assert g.boosting(a)
    run(g, C.BOOST_DURATION)
    assert a.char.head.velocity.length > crucero * 1.5
    # soltar y volver a apretar durante el cooldown no hace nada
    g.set_input(a.id, 0, 0, 1, 0)
    g.set_input(a.id, 0, 0, 1, 1)
    assert not g.boosting(a)
    run(g, C.BOOST_COOLDOWN)
    g.set_input(a.id, 0, 0, 1, 0)
    g.set_input(a.id, 0, 0, 1, 1)
    assert g.boosting(a)


def test_mantener_espacio_no_repite_el_boost():
    g, (a, b) = started_game(2)
    g.set_input(a.id, 0, 0, 0, 1)
    assert g.boosting(a)
    run(g, C.BOOST_COOLDOWN + 0.5)
    g.set_input(a.id, 0, 0, 0, 1)  # sigue apretada: no es un flanco nuevo
    assert not g.boosting(a)


def test_boost_no_funciona_en_cuenta_regresiva():
    g = Game()
    a = g.add_player("A")
    g.add_player("B")
    g.step(DT)
    assert g.phase == COUNTDOWN
    g.set_input(a.id, 0, 0, 0, 1)
    assert not g.boosting(a)
