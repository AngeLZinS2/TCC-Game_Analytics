"""Carga do ranking oficial de R6 (SI Points da Ubisoft) em `ranking_externo`.

Mesma ideia do `load_valve_standings`: casar o nome que a Ubisoft escreve
("DarkZero", "FaZe Clan", "ENTERPRISE Esports") com o que `dim_equipe` já tem
(vindo da PandaScore: "DarkZero Esports", "Falcons Esport"...). Reaproveita a
escada de reconciliação do `load_valve_standings` — os ajustes de estilo de
nome (afixo de organização grudado/solto) valem para qualquer fonte.

Não cria equipe: nome sem par fica com `id_equipe` nulo — o nome e a pontuação
seguem guardados para exibir e para a reconciliação melhorar depois.
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
from services.etl.transform_valve_standings import ResultadoRanking

logger = logging.getLogger(__name__)

FONTE = "ubi_r6"
JOGO = "rainbowsix"


def carregar(resultado: ResultadoRanking, jogo: str = JOGO) -> int:
    """Persiste um snapshot. Idempotente por `uq_ranking_externo_snapshot`."""
    if resultado.data_referencia is None or not resultado.linhas:
        logger.warning("ranking da Ubisoft vazio - nada a carregar")
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
                    "regiao": resultado.regiao,
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
        "ranking externo carregado",
        extra={
            "fonte": FONTE,
            "data_referencia": resultado.data_referencia.isoformat(),
            "linhas": len(linhas),
            "com_equipe_casada": casados,
        },
    )
    return len(linhas)
