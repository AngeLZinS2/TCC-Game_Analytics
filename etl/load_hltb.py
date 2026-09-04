"""Carga do tempo estimado pra zerar (HowLongToBeat).

Uma linha por jogo, sem tabela propria - diferente do ITAD (que tem uma
oferta por loja), aqui `dim_jogo_steam` ja basta: um `hltb_id` cacheado e os
tres tempos que a ficha mostra.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import update

from db.models import DimJogoSteam
from db.session import session_scope
from etl.transform_hltb import ResultadoHltb

logger = logging.getLogger(__name__)


def carregar(resultado: ResultadoHltb) -> int:
    """Persiste o tempo pra zerar. Devolve jogos tocados."""
    agora = datetime.now(timezone.utc)
    tocados = 0

    with session_scope() as sessao:
        # Buscado e nenhum candidato bateu: marca com "" para nao repetir.
        if resultado.sem_hltb:
            sessao.execute(
                update(DimJogoSteam)
                .where(DimJogoSteam.app_id.in_(resultado.sem_hltb))
                .values(hltb_id="", coletado_tempo_em=agora)
            )
            tocados += len(resultado.sem_hltb)

        for jogo in resultado.jogos:
            sessao.execute(
                update(DimJogoSteam)
                .where(DimJogoSteam.app_id == jogo.app_id)
                .values(
                    hltb_id=jogo.hltb_id,
                    hltb_nome=jogo.nome_hltb,
                    hltb_horas_historia=jogo.horas_historia,
                    hltb_horas_extras=jogo.horas_extras,
                    hltb_horas_completista=jogo.horas_completista,
                    coletado_tempo_em=agora,
                )
            )
            tocados += 1

    logger.info(
        "tempo do hltb carregado",
        extra={"jogos": len(resultado.jogos), "sem_hltb": len(resultado.sem_hltb)},
    )
    return tocados
