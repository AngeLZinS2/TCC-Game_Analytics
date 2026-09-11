"""Carga do resumo de avaliacoes por IA (Groq)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import update

from models.models import DimJogoSteam
from models.session import session_scope
from services.etl.transform_resumo_reviews import ResultadoResumoReviews

logger = logging.getLogger(__name__)


def carregar(resultado: ResultadoResumoReviews) -> int:
    """Persiste os resumos em `dim_jogo_steam`. Devolve jogos tocados."""
    agora = datetime.now(timezone.utc)
    tocados = 0

    with session_scope() as sessao:
        for resumo in resultado.resumos:
            sessao.execute(
                update(DimJogoSteam)
                .where(DimJogoSteam.app_id == resumo.app_id)
                .values(
                    resumo_reviews_texto=resumo.texto,
                    resumo_reviews_positivos=resumo.positivos or None,
                    resumo_reviews_negativos=resumo.negativos or None,
                    resumo_reviews_em=agora,
                    resumo_reviews_modelo=resumo.modelo or None,
                    resumo_reviews_avaliacoes=resumo.avaliacoes_usadas,
                )
            )
            tocados += 1

    logger.info("resumos de avaliacoes por IA carregados", extra={"jogos": tocados})
    return tocados
