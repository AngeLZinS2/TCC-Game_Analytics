"""Carga do ranking de Valorant do vlr.gg em `ranking_externo`.

Mesmo destino e mesma escada de reconciliacao que o `load_valve_standings` (o
ranking da Valve para CS): importa `normalizar`/`_resolver`/`_mapa_de_equipes`
de `load_liquipedia` em vez de duplicar.

**Nao cria equipe.** O que nao casar com `dim_equipe` fica com `id_equipe`
nulo - `estado()` do modelo so usa o prior de time que aparece num confronto, e
o `load_vlr` (partidas) ja e a fonte que cria os times de Valorant.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from collectors.vlr_rankings import JOGO, ResultadoRankingVlr
from db.models import DimJogo, RankingExterno
from db.session import session_scope
from etl.load_liquipedia import _mapa_de_equipes, _resolver
from etl.lotes import em_lotes

logger = logging.getLogger(__name__)

FONTE = "vlr"


def carregar(resultado: ResultadoRankingVlr) -> int:
    """Persiste um snapshot do rating, ligando cada linha a `dim_equipe`."""
    if not resultado.linhas:
        return 0

    agora = datetime.now(timezone.utc)

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == JOGO))
        if id_jogo is None:
            raise RuntimeError(
                f"jogo {JOGO!r} ausente em dim_jogo - rode `cli.py init-db`"
            )

        mapa = _mapa_de_equipes(sessao, id_jogo)

        linhas = []
        casados = 0
        for linha in resultado.linhas:
            id_equipe = _resolver(linha.equipe_nome, mapa)
            if id_equipe is not None:
                casados += 1
            linhas.append(
                {
                    "fonte": FONTE,
                    "id_jogo": id_jogo,
                    "data_referencia": resultado.data_referencia,
                    "regiao": linha.regiao,
                    "id_equipe": id_equipe,
                    "equipe_nome": linha.equipe_nome[:120],
                    "posicao": linha.posicao,
                    "pontos": linha.pontos,
                    "coletado_em": agora,
                }
            )

        for lote in em_lotes(linhas):
            stmt = pg_insert(RankingExterno).values(lote)
            atualizaveis = {
                coluna: stmt.excluded[coluna]
                for coluna in lote[0]
                if coluna
                not in ("fonte", "id_jogo", "data_referencia", "regiao", "equipe_nome")
            }
            sessao.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_ranking_externo_snapshot", set_=atualizaveis
                )
            )

    logger.info(
        "ranking de valorant do vlr.gg carregado",
        extra={
            "linhas": len(linhas),
            "casados": casados,
            "data_referencia": resultado.data_referencia.isoformat(),
        },
    )
    return len(linhas)
