"""Carga da agenda de CS do hltv.org em `agenda_partida`.

Fina: toda a lógica (reconciliar time, criar o que falta, upsert) mora em
`etl.load_agenda`. Aqui só amarra ao jogo e ao prefixo.
"""

from __future__ import annotations

from services.collectors.hltv import JOGO, ResultadoHltv
from services.etl.load_agenda import carregar_agenda


def carregar(resultado: ResultadoHltv) -> int:
    return carregar_agenda(JOGO, resultado.partidas, prefixo_equipe="hltv")
