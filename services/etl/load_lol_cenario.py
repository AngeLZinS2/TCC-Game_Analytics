"""Carga do cenario de LoL profissional.

Tres destinos, uma transacao:
- `ranking_externo` (`fonte="lolesports"`) - a classificacao por split, mesmo
  padrao/reconciliacao do `load_rlcs_rankings` (nao cria equipe la; casa por
  nome contra `dim_equipe`).
- `dim_equipe` - os times da LoL Esports, `id_externo="lolesports:<id>"`.
- `dim_jogador` - o elenco (apelido, nome civil, rota, foto, `id_equipe`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.models import DimEquipe, DimJogador, DimJogo, RankingExterno
from models.session import session_scope
from services.etl.load_liquipedia import _mapa_de_equipes
from services.etl.load_valve_standings import _resolver_valve
from services.etl.lotes import em_lotes
from services.etl.transform_lol_cenario import FONTE, JOGO, ResultadoLolCenario

logger = logging.getLogger(__name__)


def _upsert_ranking(sessao, id_jogo, resultado, agora) -> int:
    if not resultado.linhas_ranking:
        return 0
    mapa = _mapa_de_equipes(sessao, id_jogo)
    linhas = []
    for linha in resultado.linhas_ranking:
        linhas.append(
            {
                "fonte": FONTE,
                "id_jogo": id_jogo,
                "data_referencia": resultado.data_referencia,
                "regiao": linha.regiao,
                "id_equipe": _resolver_valve(linha.equipe_nome, mapa),
                "equipe_nome": linha.equipe_nome[:120],
                "posicao": linha.posicao,
                "pontos": None,
                "vitorias": linha.vitorias,
                "derrotas": linha.derrotas,
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
    return len(linhas)


def _upsert_equipes(sessao, id_jogo, resultado) -> dict[str, int]:
    if not resultado.equipes:
        return {}
    linhas = [
        {
            "id_jogo": id_jogo,
            "id_externo": e.id_externo,
            "nome": e.nome,
            "tag": e.tag,
            "logo_url": e.logo_url,
            "regiao": e.regiao,
        }
        for e in resultado.equipes
    ]
    for lote in em_lotes(linhas):
        stmt = pg_insert(DimEquipe).values(lote)
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_equipe_jogo_externo",
                set_={
                    "nome": stmt.excluded.nome,
                    "tag": stmt.excluded.tag,
                    "logo_url": stmt.excluded.logo_url,
                    "regiao": stmt.excluded.regiao,
                },
            )
        )
    sessao.flush()
    externos = [e.id_externo for e in resultado.equipes]
    return {
        ext: idq
        for idq, ext in sessao.execute(
            select(DimEquipe.id_equipe, DimEquipe.id_externo).where(
                DimEquipe.id_jogo == id_jogo, DimEquipe.id_externo.in_(externos)
            )
        )
    }


def _upsert_jogadores(sessao, id_jogo, resultado, mapa_equipes) -> int:
    if not resultado.jogadores:
        return 0
    por_equipe = {
        e.id_externo: e.regiao for e in resultado.equipes
    }
    linhas = [
        {
            "id_jogo": id_jogo,
            "id_externo": j.id_externo,
            "nome": j.nome,
            "nome_completo": j.nome_completo,
            "papel": j.papel,
            "imagem": j.imagem,
            "id_equipe": mapa_equipes.get(j.equipe_id_externo),
            "regiao": por_equipe.get(j.equipe_id_externo),
        }
        for j in resultado.jogadores
    ]
    for lote in em_lotes(linhas):
        stmt = pg_insert(DimJogador).values(lote)
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_jogador_jogo_externo",
                set_={
                    "nome": stmt.excluded.nome,
                    "nome_completo": stmt.excluded.nome_completo,
                    "papel": stmt.excluded.papel,
                    "imagem": stmt.excluded.imagem,
                    "id_equipe": stmt.excluded.id_equipe,
                    "regiao": stmt.excluded.regiao,
                },
            )
        )
    return len(linhas)


def carregar(resultado: ResultadoLolCenario, jogo: str = JOGO) -> int:
    if resultado.total == 0:
        logger.info("cenario de LoL vazio - nada a carregar")
        return 0

    agora = datetime.now(timezone.utc)
    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == jogo))
        if id_jogo is None:
            raise RuntimeError(f"jogo {jogo!r} ausente em dim_jogo")

        mapa_equipes = _upsert_equipes(sessao, id_jogo, resultado)
        jogadores = _upsert_jogadores(sessao, id_jogo, resultado, mapa_equipes)
        sessao.flush()
        ranking = _upsert_ranking(sessao, id_jogo, resultado, agora)

    logger.info(
        "cenario de LoL carregado",
        extra={
            "ranking": ranking,
            "equipes": len(mapa_equipes),
            "jogadores": jogadores,
            "regioes": sorted({r.regiao for r in resultado.linhas_ranking}),
        },
    )
    return ranking + len(mapa_equipes) + jogadores
