"""Carga dos campeoes de League of Legends.

Mesma dimensao dos herois de Dota e dos agentes de Valorant - o modelo sempre
disse que os tres sao o mesmo conceito. O que muda e a fonte e o vocabulario
das metricas, e nenhum dos dois mora aqui.
"""

from __future__ import annotations

from typing import Any

from collectors.lol_campeoes import JOGO
from etl.load_personagens import carregar


def carregar_campeoes(campeoes: list[dict[str, Any]]) -> int:
    return carregar(JOGO, campeoes, fonte="opgg")
