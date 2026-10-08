"""Lógica pura de cadenas (sin física).

Una cadena es una lista de jugadores ordenada de adelante hacia atrás. El
piloto maneja la cabeza del primer miembro. Solo los testículos del último
miembro están libres para ser penetrados.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Chain:
    id: int
    members: list[str] = field(default_factory=list)
    pilot: str | None = None

    @property
    def front(self) -> str:
        return self.members[0]

    @property
    def last(self) -> str:
        return self.members[-1]


def merge(target: Chain, attacker: Chain) -> Chain:
    """El frente de `attacker` penetró la cola de `target`.

    El piloto atacante pasa a manejar el frente de `target`, con toda su
    cadena acoplada atrás. Conserva el id de `target`.
    """
    if target.id == attacker.id:
        raise ValueError("una cadena no puede penetrarse a sí misma")
    return Chain(target.id, target.members + attacker.members, attacker.pilot)


def on_disconnect(chain: Chain, pid: str, connected: set[str]) -> None:
    """Si se fue el piloto, el control pasa al conectado más cercano al final."""
    if chain.pilot != pid:
        return
    chain.pilot = next((m for m in reversed(chain.members) if m in connected and m != pid), None)


def winner(chains: list[Chain], connected: set[str]) -> Chain | None:
    """La cadena que contiene a todos los jugadores conectados, si existe."""
    if not connected:
        return None
    for c in chains:
        if c.pilot is not None and connected <= set(c.members):
            return c
    return None
