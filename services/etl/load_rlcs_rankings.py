"""Carga do leaderboard da RLCS em `ranking_externo` (`fonte="rlcs"`).

Mesmo destino e mesma escada de reconciliação do `load_vlr_rankings` /
`load_ubi_r6`. Não cria equipe - o que não casar com `dim_equipe` fica com
`id_equipe` nulo (o coletor de partidas do PandaScore é quem cria os times de
Rocket League).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.models import DimJogo, RankingExterno
from models.session import session_scope
from services.etl.load_liquipedia import _mapa_de_equipes
from services.etl.load_valve_standings import _resolver_valve
from services.etl.lotes import em_lotes
from services.etl.transform_rlcs_rankings import FONTE, JOGO, ResultadoRanking

logger = logging.getLogger(__name__)


def carregar(resultado: ResultadoRanking, jogo: str = JOGO) -> int:
    if not resultado.linhas:
        logger.info("leaderboard da RLCS vazio - nada a carregar")
        return 0

    agora = datetime.now(timezone.utc)

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == jogo))
        if id_jogo is None:
            raise RuntimeError(f"jogo {jogo!r} ausente em dim_jogo")

        mapa = _mapa_de_equipes(sessao, id_jogo)

        linhas = []
        casados = 0
        for linha in resultado.linhas:
            id_equipe = _resolver_valve(linha.equipe_nome, mapa)
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
        "leaderboard da RLCS carregado",
        extra={
            "fonte": FONTE,
            "data_referencia": resultado.data_referencia.isoformat(),
            "linhas": len(linhas),
            "com_equipe_casada": casados,
            "regioes": sorted({linha.regiao for linha in resultado.linhas}),
        },
    )
    return len(linhas)
