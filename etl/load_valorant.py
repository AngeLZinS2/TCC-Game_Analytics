"""Carga dos agentes do VALORANT em `dim_personagem`.

Mesma dimensao dos herois de Dota, mesma restricao `(id_jogo, id_externo)` - e
de proposito. O modelo sempre disse que heroi, campeao e agente sao o mesmo
conceito; ate aqui so um dos tres estava preenchido.
"""

from __future__ import annotations

import logging
from typing import Any

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from collectors.valorant_agentes import JOGO
from db.models import DimJogo, DimPersonagem, FatoEstatisticaPersonagem
from db.session import session_scope

logger = logging.getLogger(__name__)


class JogoNaoCadastradoError(RuntimeError):
    """dim_jogo e semeada pelas migrations; sem ela nada pode ser carregado."""


def carregar_agentes(agentes: list[dict[str, Any]]) -> int:
    """Upsert do elenco. Devolve quantos agentes entraram na instrucao."""
    if not agentes:
        return 0

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == JOGO))
        if id_jogo is None:
            raise JogoNaoCadastradoError(
                f"jogo {JOGO!r} ausente em dim_jogo - rode as migrations "
                "(python cli.py init-db)"
            )

        linhas = [
            {
                "id_jogo": id_jogo,
                "id_externo": agente["id_externo"],
                "nome": agente["nome"],
                "nome_interno": agente.get("nome_interno"),
                "papel": agente.get("papel"),
            }
            # `habilidades` fica de fora: nao ha coluna, e criar uma tabela
            # para um dado que nenhuma tela le ainda seria schema por
            # antecipacao. O payload cru guarda tudo, entao nada se perde.
            for agente in agentes
        ]

        stmt = pg_insert(DimPersonagem).values(linhas)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_personagem_jogo_externo",
            set_={
                "nome": stmt.excluded.nome,
                "nome_interno": stmt.excluded.nome_interno,
                "papel": stmt.excluded.papel,
            },
        )
        sessao.execute(stmt)

    logger.info("agentes de valorant carregados", extra={"agentes": len(linhas)})
    return len(linhas)


def carregar_estatisticas(agentes: list[dict[str, Any]]) -> int:
    """Snapshot das metricas agregadas de cada agente.

    So grava quem veio COM metrica: agente sem numero nao vira linha de zeros -
    a diferenca entre "o OP.GG nao publicou" e "e zero" e exatamente o que a
    tela precisa poder dizer.

    A janela e truncada na hora, como `fato_snapshot_jogo_steam`: duas coletas
    na mesma hora viram um UPDATE em vez de duas linhas, e a serie fica com o
    grao que a coleta realmente tem.
    """
    com_numero = [a for a in agentes if a.get("metricas")]
    if not com_numero:
        return 0

    janela = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == JOGO))
        if id_jogo is None:
            raise JogoNaoCadastradoError(f"jogo {JOGO!r} ausente em dim_jogo")

        chaves = {
            id_externo: id_personagem
            for id_externo, id_personagem in sessao.execute(
                select(DimPersonagem.id_externo, DimPersonagem.id_personagem).where(
                    DimPersonagem.id_jogo == id_jogo
                )
            )
        }

        linhas = [
            {
                "id_personagem": chaves[agente["id_externo"]],
                "janela_coleta": janela,
                "fonte": "opgg",
                "partidas": agente.get("partidas"),
                "vitorias": agente.get("vitorias"),
                "metricas": agente["metricas"],
            }
            for agente in com_numero
            if agente["id_externo"] in chaves
        ]
        if not linhas:
            return 0

        stmt = pg_insert(FatoEstatisticaPersonagem).values(linhas)
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_estatistica_personagem_janela",
                set_={
                    "partidas": stmt.excluded.partidas,
                    "vitorias": stmt.excluded.vitorias,
                    "metricas": stmt.excluded.metricas,
                },
            )
        )

    logger.info("estatistica de agentes carregada", extra={"agentes": len(linhas)})
    return len(linhas)
