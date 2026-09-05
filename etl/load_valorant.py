"""Carga dos agentes do VALORANT em `dim_personagem`.

Mesma dimensao dos herois de Dota e dos campeoes de League - o modelo sempre
disse que os tres sao o mesmo conceito. A mecanica de gravar e compartilhada em
`etl/load_personagens.py`; o que e especifico do Valorant (quais metricas
existem e de que bruto saem) mora no coletor.
"""

from __future__ import annotations

from typing import Any

from collectors.valorant_agentes import JOGO
from etl.load_personagens import JogoNaoCadastradoError, carregar

__all__ = ["JogoNaoCadastradoError", "carregar_agentes", "carregar_estatisticas"]


def carregar_agentes(agentes: list[dict[str, Any]]) -> int:
    """Elenco + snapshot das metricas, numa transacao so."""
    return carregar(JOGO, agentes, fonte="opgg")


def carregar_estatisticas(agentes: list[dict[str, Any]]) -> int:
    """Mantido pelo nome antigo: `carregar_agentes` ja grava o snapshot.

    Existia quando as duas cargas eram separadas. Virou no-op em vez de sumir
    porque a CLI e o coletor a chamavam - e um no-op declarado e mais honesto
    que uma segunda gravacao do mesmo dado.
    """
    return 0
