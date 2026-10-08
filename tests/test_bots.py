import math
import random

from server import config as C
from server.game import COUNTDOWN, LOBBY, PLAYING, ROUND_OVER, Game
from test_sim import DT, place, run


def test_humano_mas_bot_arranca_la_ronda():
    g = Game()
    g.add_player("humano")
    bot = g.add_bot()
    assert bot.bot and bot.name.startswith("🤖")
    g.step(DT)
    assert g.phase == COUNTDOWN


def test_solo_bots_no_juegan():
    g = Game()
    g.add_bot()
    g.add_bot()
    run(g, 1)
    assert g.phase == LOBBY


def test_si_se_van_los_humanos_vuelve_al_lobby():
    g = Game()
    h = g.add_player("humano")
    g.add_bot()
    g.add_bot()
    run(g, C.COUNTDOWN_S + 0.5)
    assert g.phase == PLAYING
    g.remove_player(h.id)
    g.step(DT)
    assert g.phase == LOBBY
    assert sum(p.bot for p in g.players.values()) == 2  # los bots quedan esperando


def test_remove_bot_saca_el_ultimo():
    g = Game()
    g.add_player("humano")
    a, b = g.add_bot(), g.add_bot()
    g.remove_bot()
    assert b.id not in g.players and a.id in g.players
    g.remove_bot()
    g.remove_bot()  # sin bots no hace nada
    assert [p.name for p in g.players.values()] == ["humano"]


def test_nombres_de_bots_no_se_repiten():
    g = Game()
    names = [g.add_bot().name for _ in range(5)]
    assert len(set(names)) == 5


def test_bot_conquista_a_un_humano_quieto():
    random.seed(0)
    g = Game()
    h = g.add_player("humano")
    bot = g.add_bot()
    run(g, C.COUNTDOWN_S + 0.1)
    # el humano en el medio de un hueco libre, el bot lejos y de costado
    place(g, {h: (1200, 300, 0), bot: (600, 1000, -math.pi / 2)})
    for _ in range(30 * C.PHYSICS_HZ):
        g.step(DT)
        if g.phase == ROUND_OVER:
            break
    assert g.phase == ROUND_OVER and g.winner == bot.id


def test_bot_conquistado_sabotea():
    random.seed(0)
    g = Game()
    h = g.add_player("humano")
    bot = g.add_bot()
    run(g, C.COUNTDOWN_S + 0.1)
    place(g, {bot: (1300, 280, 0), h: (1100, 280, 0)})
    g.set_input(h.id, 0, 0, 1)
    run(g, 1.5)
    assert g.chains[bot.chain_id].pilot == h.id
    seen = set()
    for _ in range(3 * C.PHYSICS_HZ):
        g.step(DT)
        seen.add((bot.input["l"], bot.input["r"]))
    assert {(1, 0), (0, 1)} <= seen
