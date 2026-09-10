"""Carga do catalogo Xbox (Game Pass + Microsoft Store) no PostgreSQL.

Idempotencia: a dimensao faz upsert por `product_id`, o snapshot por
`(product_id, janela_coleta)`. Rodar o coletor duas vezes na mesma janela
atualiza as linhas em vez de duplicar a serie.

`game_pass_desde` e o unico campo que NAO segue o upsert cego: e a data em que
vimos o jogo no Game Pass pela primeira vez, entao so preenche (nunca
reescreve) - `func.coalesce` mantem o valor antigo e so carimba `current_date`
quando ainda era nulo e o jogo esta no GP agora.
"""

from __future__ import annotations

import logging

from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models.models import DimJogoXbox, FatoSnapshotJogoXbox
from models.session import session_scope
from services.etl.lotes import em_lotes
from services.etl.transform_xbox import ResultadoXbox

logger = logging.getLogger(__name__)


def _upsert_jogos(sessao: Session, resultado: ResultadoXbox) -> int:
    if not resultado.jogos:
        return 0

    linhas = [jogo.model_dump() for jogo in resultado.jogos]
    total = 0
    for lote in em_lotes(linhas):
        stmt = pg_insert(DimJogoXbox).values(lote)
        atualizaveis = {
            coluna: stmt.excluded[coluna]
            for coluna in lote[0]
            if coluna != "product_id"
        }
        atualizaveis["atualizado_em"] = func.now()
        # So preenche a primeira vez: mantem a data antiga; se ainda e nula e o
        # jogo entrou no GP, carimba hoje; senao continua nula.
        atualizaveis["game_pass_desde"] = func.coalesce(
            DimJogoXbox.game_pass_desde,
            case((stmt.excluded.no_game_pass.is_(True), func.current_date())),
        )
        sessao.execute(
            stmt.on_conflict_do_update(
                index_elements=["product_id"], set_=atualizaveis
            )
        )
        total += len(lote)
    return total


def _upsert_snapshots(sessao: Session, resultado: ResultadoXbox) -> int:
    if not resultado.snapshots:
        return 0

    linhas = [snap.model_dump() for snap in resultado.snapshots]
    total = 0
    for lote in em_lotes(linhas):
        stmt = pg_insert(FatoSnapshotJogoXbox).values(lote)
        atualizaveis = {
            coluna: stmt.excluded[coluna]
            for coluna in lote[0]
            if coluna not in ("product_id", "janela_coleta")
        }
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_snapshot_xbox_janela", set_=atualizaveis
            )
        )
        total += len(lote)
    return total


def carregar(resultado: ResultadoXbox) -> int:
    """Persiste dimensao e snapshot numa unica transacao. Retorna linhas afetadas."""
    with session_scope() as sessao:
        jogos = _upsert_jogos(sessao, resultado)
        # O snapshot tem FK para a dimensao: flush antes.
        sessao.flush()
        snapshots = _upsert_snapshots(sessao, resultado)

    logger.info(
        "carga xbox concluida",
        extra={"jogos": jogos, "snapshots": snapshots},
    )
    return jogos + snapshots
