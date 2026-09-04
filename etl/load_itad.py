"""Carga dos precos do IsThereAnyDeal.

- `dim_jogo_steam`: cacheia o `itad_id` (ou `""` quando o jogo nao existe no
  ITAD) e guarda o menor preco historico.
- `oferta_jogo_steam`: uma linha por loja. A cada rodada as ofertas de um jogo
  sao substituidas inteiras - uma loja que sumiu do resultado sai do banco,
  senao a tela mostraria preco velho de uma promo que ja acabou.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import DimJogoSteam, OfertaJogoSteam
from db.session import session_scope
from etl.transform_itad import ResultadoItad

logger = logging.getLogger(__name__)


def carregar(resultado: ResultadoItad) -> int:
    """Persiste ofertas e menor preco historico. Devolve linhas tocadas."""
    agora = datetime.now(timezone.utc)
    ofertas_gravadas = 0
    jogos_tocados = 0

    with session_scope() as sessao:
        # Jogos que nao existem no ITAD: marca com "" para nao procurar de novo.
        if resultado.sem_itad:
            sessao.execute(
                update(DimJogoSteam)
                .where(DimJogoSteam.app_id.in_(resultado.sem_itad))
                .values(itad_id="", coletado_preco_em=agora)
            )

        for jogo in resultado.jogos:
            valores: dict = {"itad_id": jogo.itad_id, "coletado_preco_em": agora}
            if jogo.menor_historico is not None:
                valores.update(
                    menor_preco_historico=jogo.menor_historico.preco,
                    menor_preco_historico_loja=jogo.menor_historico.loja,
                    menor_preco_historico_moeda=jogo.menor_historico.moeda,
                    menor_preco_historico_em=jogo.menor_historico.data,
                )
            sessao.execute(
                update(DimJogoSteam)
                .where(DimJogoSteam.app_id == jogo.app_id)
                .values(**valores)
            )
            jogos_tocados += 1

            # Substitui as ofertas do jogo inteiras.
            sessao.execute(
                OfertaJogoSteam.__table__.delete().where(
                    OfertaJogoSteam.app_id == jogo.app_id
                )
            )
            if not jogo.ofertas:
                continue

            # Dedup por loja_id no proprio lote (o ITAD as vezes repete a loja
            # com e sem voucher).
            por_loja: dict[int, dict] = {}
            for oferta in jogo.ofertas:
                por_loja[oferta.loja_id] = {
                    "app_id": jogo.app_id,
                    "loja_id": oferta.loja_id,
                    "loja": oferta.loja[:60],
                    "preco": oferta.preco,
                    "preco_normal": oferta.preco_normal,
                    "desconto": oferta.desconto,
                    "moeda": oferta.moeda,
                    "url": oferta.url,
                    "drm": (oferta.drm or None) and oferta.drm[:120],
                    "coletado_em": agora,
                }
            linhas = list(por_loja.values())
            # Sem ON CONFLICT: as linhas do jogo ja foram apagadas acima, e o
            # dict `por_loja` garante loja_id unico no lote.
            sessao.execute(pg_insert(OfertaJogoSteam).values(linhas))
            ofertas_gravadas += len(linhas)

    logger.info(
        "precos do itad carregados",
        extra={
            "jogos": jogos_tocados,
            "ofertas": ofertas_gravadas,
            "sem_itad": len(resultado.sem_itad),
        },
    )
    return jogos_tocados + ofertas_gravadas
