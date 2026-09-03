"""Carga do dominio catalogo/mercado (Steam) no PostgreSQL.

Idempotencia: a dimensao faz upsert por `app_id`, o snapshot por
`(app_id, janela_coleta)` e a avaliacao por `(app_id, recommendationid)`.
Rodar o coletor duas vezes na mesma janela atualiza as linhas em vez de
duplicar a serie temporal.
"""

from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models import DimJogoSteam, FatoAvaliacaoSteam, FatoSnapshotJogoSteam
from db.session import session_scope
from etl.lotes import em_lotes
from etl.transform_steam import ResultadoSteam

logger = logging.getLogger(__name__)


def _upsert_jogos(sessao: Session, resultado: ResultadoSteam) -> int:
    if not resultado.jogos:
        return 0

    linhas = [jogo.model_dump() for jogo in resultado.jogos]
    stmt = pg_insert(DimJogoSteam).values(linhas)
    atualizaveis = {
        coluna: stmt.excluded[coluna]
        for coluna in linhas[0]
        if coluna != "app_id"
    }
    atualizaveis["atualizado_em"] = func.now()
    stmt = stmt.on_conflict_do_update(index_elements=["app_id"], set_=atualizaveis)
    sessao.execute(stmt)
    return len(linhas)


def _upsert_snapshots(sessao: Session, resultado: ResultadoSteam) -> int:
    if not resultado.snapshots:
        return 0

    linhas = [snap.model_dump() for snap in resultado.snapshots]
    stmt = pg_insert(FatoSnapshotJogoSteam).values(linhas)
    atualizaveis = {
        coluna: stmt.excluded[coluna]
        for coluna in linhas[0]
        if coluna not in ("app_id", "janela_coleta")
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_snapshot_app_janela", set_=atualizaveis
    )
    sessao.execute(stmt)
    return len(linhas)


def _upsert_avaliacoes(sessao: Session, resultado: ResultadoSteam) -> int:
    """Idempotente por `(app_id, recommendationid)`.

    O texto entra no `set_` do conflito porque a Steam permite editar uma
    avaliacao: o `recommendationid` continua o mesmo e o conteudo muda. Ignorar
    o conflito congelaria a versao antiga no banco.
    """
    if not resultado.avaliacoes:
        return 0

    linhas = [avaliacao.model_dump() for avaliacao in resultado.avaliacoes]

    # Em lotes: com 12 colunas, dez mil avaliacoes num INSERT so passariam do
    # limite de parametros do Postgres.
    for lote in em_lotes(linhas):
        stmt = pg_insert(FatoAvaliacaoSteam).values(lote)
        atualizaveis = {
            coluna: stmt.excluded[coluna]
            for coluna in lote[0]
            if coluna not in ("app_id", "id_externo")
        }
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_avaliacao_app_externo", set_=atualizaveis
            )
        )

    return len(linhas)


def carregar(resultado: ResultadoSteam) -> int:
    """Persiste dimensao e fatos numa unica transacao. Retorna linhas afetadas."""
    with session_scope() as sessao:
        jogos = _upsert_jogos(sessao, resultado)
        # Os fatos tem FK para a dimensao: o flush precisa acontecer antes.
        sessao.flush()
        snapshots = _upsert_snapshots(sessao, resultado)
        avaliacoes = _upsert_avaliacoes(sessao, resultado)

    logger.info(
        "carga steam concluida",
        extra={"jogos": jogos, "snapshots": snapshots, "avaliacoes": avaliacoes},
    )
    return jogos + snapshots + avaliacoes
