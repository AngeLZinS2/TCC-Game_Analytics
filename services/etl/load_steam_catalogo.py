"""Carga do indice de catalogo completo da Steam (Fase 35).

Duas responsabilidades por execucao, na mesma transacao:

1. Upsert em `dim_app_steam_nome` - o indice do catalogo completo. Marca
   `pendente_atualizacao_preco` SO quando `numero_mudanca_preco` recebido e
   DIFERENTE (`!=`) do que ja estava salvo, e so quando ja havia um valor
   salvo (evita marcar o catalogo inteiro como pendente na carga inicial,
   quando toda linha e nova).
2. Upsert do checkpoint em `steam_sincronizacao` - contadores cumulativos e
   `status`, para a proxima execucao saber de onde retomar.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models.models import DimAppSteamNome, SincronizacaoSteam
from models.session import session_scope
from services.etl.lotes import em_lotes
from services.etl.transform_steam_catalogo import ResultadoCatalogoSteam

logger = logging.getLogger(__name__)


def _upsert_catalogo(sessao: Session, resultado: ResultadoCatalogoSteam) -> tuple[int, int]:
    """Upsert em `dim_app_steam_nome`. Devolve (criados, atualizados)."""
    if not resultado.linhas:
        return 0, 0

    agora = datetime.now(timezone.utc)
    ids = [linha.app_id for linha in resultado.linhas]
    existentes = set(
        sessao.scalars(
            select(DimAppSteamNome.app_id).where(DimAppSteamNome.app_id.in_(ids))
        )
    )

    linhas = [
        {
            "app_id": linha.app_id,
            "nome": linha.nome,
            "tipo": linha.tipo,
            "ultima_modificacao": linha.ultima_modificacao,
            "numero_mudanca_preco": linha.numero_mudanca_preco,
            "visto_em": agora,
        }
        for linha in resultado.linhas
    ]

    for lote in em_lotes(linhas):
        stmt = pg_insert(DimAppSteamNome).values(lote)
        stmt = stmt.on_conflict_do_update(
            index_elements=["app_id"],
            set_={
                "nome": stmt.excluded.nome,
                "tipo": stmt.excluded.tipo,
                "ultima_modificacao": stmt.excluded.ultima_modificacao,
                "numero_mudanca_preco": stmt.excluded.numero_mudanca_preco,
                "visto_em": stmt.excluded.visto_em,
                # Marca pendente so quando ja havia um numero salvo E ele
                # mudou - nunca no primeiro avistamento do app (a carga
                # inicial nao pode inundar a fila de preco do catalogo
                # inteiro). Fica pendente se ja estava (nao "desmarca"
                # aqui - so `load_steam.py` desmarca, apos reprocessar).
                "pendente_atualizacao_preco": (
                    DimAppSteamNome.pendente_atualizacao_preco
                    | (
                        DimAppSteamNome.numero_mudanca_preco.is_not(None)
                        & stmt.excluded.numero_mudanca_preco.is_not(None)
                        & (
                            DimAppSteamNome.numero_mudanca_preco
                            != stmt.excluded.numero_mudanca_preco
                        )
                    )
                ),
            },
        )
        sessao.execute(stmt)

    ids_unicos = set(ids)
    atualizados = len(existentes)
    criados = len(ids_unicos) - len(existentes)
    return criados, atualizados


def _upsert_checkpoint(
    sessao: Session, resultado: ResultadoCatalogoSteam, criados: int, atualizados: int
) -> None:
    agora = datetime.now(timezone.utc)
    status = "concluido" if resultado.concluido else "em_andamento"

    stmt = pg_insert(SincronizacaoSteam).values(
        tipo_sincronizacao=resultado.fase,
        status=status,
        last_appid=resultado.last_appid,
        iniciada_em=agora,
        concluida_em=agora if resultado.concluido else None,
        registros_processados=resultado.total,
        registros_criados=criados,
        registros_atualizados=atualizados,
        registros_falhos=0,
        atualizado_em=agora,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_steam_sincronizacao_tipo",
        set_={
            "status": stmt.excluded.status,
            # `last_appid` so avanca se esta execucao trouxe pagina nova -
            # um tick sem apps (falha logo na 1a chamada) preserva o cursor.
            "last_appid": (
                stmt.excluded.last_appid
                if resultado.last_appid is not None
                else SincronizacaoSteam.last_appid
            ),
            "concluida_em": stmt.excluded.concluida_em,
            "registros_processados": (
                SincronizacaoSteam.registros_processados + stmt.excluded.registros_processados
            ),
            "registros_criados": (
                SincronizacaoSteam.registros_criados + stmt.excluded.registros_criados
            ),
            "registros_atualizados": (
                SincronizacaoSteam.registros_atualizados + stmt.excluded.registros_atualizados
            ),
            "atualizado_em": stmt.excluded.atualizado_em,
        },
    )
    sessao.execute(stmt)


def carregar(resultado: ResultadoCatalogoSteam) -> int:
    """Persiste o indice do catalogo + o checkpoint numa unica transacao."""
    if resultado.fase == "sem_execucao":
        logger.debug("sync incremental do catalogo Steam: fora da janela, no-op")
        return 0

    with session_scope() as sessao:
        criados, atualizados = _upsert_catalogo(sessao, resultado)
        _upsert_checkpoint(sessao, resultado, criados, atualizados)

    logger.info(
        "carga do catalogo Steam concluida",
        extra={
            "fase": resultado.fase,
            "paginas": resultado.paginas_processadas,
            "apps": resultado.total,
            "criados": criados,
            "atualizados": atualizados,
            "last_appid": resultado.last_appid,
            "concluido": resultado.concluido,
        },
    )
    return resultado.total
