"""Carga do ranking de Dota 2 do DLTV em `ranking_externo` (`fonte="dltv"`).

Mesmo destino e mesma escada de reconciliação do `load_vlr_rankings` /
`load_ubi_r6`. Não cria equipe - o que não casar com `dim_equipe` fica com
`id_equipe` nulo (a OpenDota é quem cria os times de Dota 2).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import DimJogo, RankingExterno
from db.session import session_scope
from etl.load_agenda import _preencher_escudos
from etl.load_liquipedia import _mapa_de_equipes
from etl.load_valve_standings import _resolver_valve
from etl.lotes import em_lotes
from etl.transform_dltv_ranking import FONTE, JOGO, REGIAO, ResultadoRanking

logger = logging.getLogger(__name__)


def carregar(resultado: ResultadoRanking, jogo: str = JOGO) -> int:
    if not resultado.linhas:
        logger.info("ranking do DLTV vazio - nada a carregar")
        return 0

    agora = datetime.now(timezone.utc)

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == jogo))
        if id_jogo is None:
            raise RuntimeError(f"jogo {jogo!r} ausente em dim_jogo")

        mapa = _mapa_de_equipes(sessao, id_jogo)

        # O DLTV traz o escudo de todo time do top 50; a maioria dos times de
        # tier-1 não está nas nossas partidas (que são de tier-2), então o
        # `dim_equipe` deles nasceu sem logo. Backfill só onde está nulo.
        meta_time = {
            linha.equipe_nome: (linha.logo_url, None)
            for linha in resultado.linhas
            if linha.logo_url
        }
        _preencher_escudos(sessao, id_jogo, mapa, meta_time)

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
                    "regiao": REGIAO,
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
        "ranking de Dota 2 do DLTV carregado",
        extra={
            "fonte": FONTE,
            "data_referencia": resultado.data_referencia.isoformat(),
            "linhas": len(linhas),
            "com_equipe_casada": casados,
        },
    )
    return len(linhas)
