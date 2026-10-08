import pytest

from server.chains import Chain, merge, on_disconnect, winner


def test_merge_simple():
    a, b = Chain(1, ["A"], "A"), Chain(2, ["B"], "B")
    c = merge(b, a)  # A penetra a B
    assert c.members == ["B", "A"]
    assert c.pilot == "A"
    assert c.id == 2


def test_tercero_toma_toda_la_cadena():
    ba = Chain(2, ["B", "A"], "A")
    c = merge(ba, Chain(3, ["C"], "C"))
    assert c.members == ["B", "A", "C"]
    assert c.pilot == "C"


def test_cadena_contra_cadena():
    ef = Chain(5, ["E", "F"], "F")
    ba = Chain(2, ["B", "A"], "A")
    c = merge(ef, ba)  # el frente de [B,A] (piloteado por A) penetra la cola de F
    assert c.members == ["E", "F", "B", "A"]
    assert c.pilot == "A"


def test_no_se_penetra_a_si_misma():
    c = Chain(1, ["A"], "A")
    with pytest.raises(ValueError):
        merge(c, c)


def test_desconexion_del_piloto():
    c = Chain(1, ["B", "A", "C"], "C")
    on_disconnect(c, "C", {"A", "B"})
    assert c.pilot == "A"


def test_desconexion_de_no_piloto():
    c = Chain(1, ["B", "A", "C"], "C")
    on_disconnect(c, "A", {"B", "C"})
    assert c.pilot == "C"


def test_desconexion_sin_nadie_conectado():
    c = Chain(1, ["B", "A"], "A")
    on_disconnect(c, "A", set())
    assert c.pilot is None


def test_winner():
    chains = [Chain(1, ["B", "A"], "A"), Chain(3, ["C"], "C")]
    assert winner(chains, {"A", "B", "C"}) is None
    chains = [Chain(1, ["B", "A", "C"], "C")]
    assert winner(chains, {"A", "B", "C"}).pilot == "C"
    # los desconectados no cuentan
    assert winner([Chain(1, ["B", "A"], "A")], {"A"}).pilot == "A"
    # una cadena inerte (sin piloto) no gana
    assert winner([Chain(1, ["B", "A"], None)], {"B"}) is None
