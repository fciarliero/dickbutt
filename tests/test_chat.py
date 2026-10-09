import pytest

from server import bots
from server import config as C
from server.game import Game
from test_sim import DT, run


def chats(game):
    return [e for e in game.drain_events() if e["kind"] == "chat"]


def test_mensaje_sale_como_evento_y_queda_en_el_historial():
    g = Game()
    a = g.add_player("Ana")
    g.drain_events()
    assert g.chat(a.id, "  hola  ")
    [msg] = chats(g)
    assert msg["who"] == a.id and msg["name"] == "Ana" and msg["color"] == a.color
    assert msg["text"] == "hola" and msg["bot"] is False
    assert list(g.chat_log) == [msg]


def test_recorta_y_limpia():
    g = Game()
    a = g.add_player("Ana")
    assert not g.chat(a.id, "")
    assert not g.chat(a.id, "   \n\t ")
    assert g.chat(a.id, "x" * 500)
    assert g.chat(a.id, "ho\nla\x00!")
    texts = [m["text"] for m in g.chat_log]
    assert texts == ["x" * C.CHAT_MAX, "hola!"]


def test_jugador_desconocido_o_desconectado_no_habla():
    g = Game()
    assert not g.chat("p99", "hola")
    a = g.add_player("Ana")
    g.remove_player(a.id)
    assert not g.chat(a.id, "hola")


def test_limite_de_spam():
    g = Game()
    a = g.add_player("Ana")
    sent = [g.chat(a.id, f"m{i}") for i in range(C.CHAT_RATE_N + 2)]
    assert sent == [True] * C.CHAT_RATE_N + [False, False]
    run(g, C.CHAT_RATE_S)
    assert g.chat(a.id, "de nuevo")


def test_historial_con_tope():
    g = Game()
    players = [g.add_player(f"j{i}") for i in range(C.MAX_PLAYERS)]
    for k in range(C.CHAT_HISTORY // C.CHAT_RATE_N + 2):
        for p in players[:C.CHAT_RATE_N]:
            g.chat(p.id, f"{k}")
        run(g, C.CHAT_RATE_S)
    assert len(g.chat_log) == C.CHAT_HISTORY


def test_bot_conquistado_dice_algo(monkeypatch):
    monkeypatch.setattr(bots, "BOT_CHAT_CHANCE", 1.0)
    g = Game()
    h = g.add_player("humano")
    bot = g.add_bot()
    run(g, C.COUNTDOWN_S + 0.1)
    g.drain_events()
    # acople directo, sin depender de la IA ni de la física
    g._couple(g.chains[h.chain_id], g.chains[bot.chain_id])
    assert not chats(g)  # todavía "está escribiendo"
    run(g, bots.BOT_CHAT_DELAY_S[1] + DT)
    [msg] = chats(g)
    assert msg["who"] == bot.id and msg["bot"] is True
    assert msg["text"] in bots.LINES["conquered"]


def test_bots_no_spamean(monkeypatch):
    monkeypatch.setattr(bots, "BOT_CHAT_CHANCE", 1.0)
    g = Game()
    g.add_player("humano")
    b1, b2 = g.add_bot(), g.add_bot()
    bots.react(g, "conquered", b1.id)
    bots.react(g, "conquered", b1.id)  # el mismo bot, enseguida
    bots.react(g, "conquer", b2.id)  # otro bot, dentro del silencio global
    assert len(g.pending_chat) == 1
    run(g, bots.BOT_CHAT_DELAY_S[1] + bots.BOT_CHAT_GAP_S + DT)  # el peor caso del retraso al azar
    assert len(chats(g)) == 1
    bots.react(g, "conquer", b2.id)  # pasó el silencio global: otro bot ya puede
    assert len(g.pending_chat) == 1


def test_humanos_no_reaccionan(monkeypatch):
    monkeypatch.setattr(bots, "BOT_CHAT_CHANCE", 1.0)
    g = Game()
    h = g.add_player("humano")
    bots.react(g, "win", h.id)
    bots.react(g, "win", None)
    assert not g.pending_chat


@pytest.mark.parametrize("kind", sorted(bots.LINES))
def test_frases_validas(kind):
    for line in bots.LINES[kind]:
        assert 0 < len(line) <= C.CHAT_MAX
