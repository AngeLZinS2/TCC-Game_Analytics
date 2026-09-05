"""Carga do dado estatico dos herois de Dota.

So mexe em `dim_personagem.metadados` - os herois em si ja vem da ingestao de
partidas. A mecanica de upsert e a mesma de Valorant e LoL, em
`etl/load_personagens.py`; aqui so entra a fonte.
"""

from __future__ import annotations

from typing import Any

from collectors.dota_herois import JOGO
from etl.load_personagens import carregar


def carregar_herois(herois: list[dict[str, Any]]) -> int:
    # `fonte="valve"` marca a procedencia dos metadados; nao ha metrica aqui,
    # entao nenhum snapshot novo em `fato_estatistica_personagem`.
    return carregar(JOGO, herois, fonte="valve")
