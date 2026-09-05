"""Carga dos confrontos de LoL do OP.GG em `dim_equipe` + `agenda_partida`.

As equipes entram primeiro porque o confronto referencia elas: `agenda_partida`
guarda o nome COMO VEIO (para a tela mostrar o confronto de qualquer jeito) e a
FK ao lado, e a FK so pode ser resolvida depois que a dimensao existe.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from collectors.opgg_esports import JOGO, ResultadoOpggEsports
from db.models import AgendaPartida, DimEquipe, DimJogo
from db.session import session_scope

logger = logging.getLogger(__name__)


class JogoNaoCadastradoError(RuntimeError):
    """dim_jogo e semeada pelas migrations; sem ela nada pode ser carregado."""


def carregar(resultado: ResultadoOpggEsports) -> int:
    """Persiste equipes e confrontos. Devolve quantos confrontos entraram."""
    if not resultado.confrontos:
        return 0

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == JOGO))
        if id_jogo is None:
            raise JogoNaoCadastradoError(
                f"jogo {JOGO!r} ausente em dim_jogo - rode as migrations "
                "(python cli.py init-db)"
            )

        if resultado.equipes:
            stmt = pg_insert(DimEquipe).values(
                [
                    {
                        "id_jogo": id_jogo,
                        "id_externo": equipe.id_externo,
                        "nome": equipe.nome,
                        "tag": equipe.tag,
                        "logo_url": equipe.logo_url,
                    }
                    for equipe in resultado.equipes
                ]
            )
            # Nao mexe em `regiao`, `pais`, `ativa`, `criada_em` nem
            # `pagina_liquipedia`: quem preenche esses e a wiki, e sobrescrever
            # com nulo apagaria dado melhor que ja estivesse la.
            sessao.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_equipe_jogo_externo",
                    set_={
                        "nome": stmt.excluded.nome,
                        "tag": stmt.excluded.tag,
                        "logo_url": stmt.excluded.logo_url,
                    },
                )
            )

        mapa = {
            id_externo: id_equipe
            for id_externo, id_equipe in sessao.execute(
                select(DimEquipe.id_externo, DimEquipe.id_equipe).where(
                    DimEquipe.id_jogo == id_jogo
                )
            )
        }

        agora = datetime.now(timezone.utc)
        linhas = [
            {
                "id_jogo": id_jogo,
                "id_externo": confronto.id_externo,
                "equipe_a_nome": confronto.equipe_a_nome,
                "equipe_b_nome": confronto.equipe_b_nome,
                "id_equipe_a": mapa.get(confronto.equipe_a_externo),
                "id_equipe_b": mapa.get(confronto.equipe_b_externo),
                "inicio_previsto": confronto.inicio_previsto,
                "torneio": confronto.torneio,
                "formato": confronto.formato,
                "coletado_em": agora,
                "vitoria_a": confronto.vitoria_a,
                "placar_a": confronto.placar_a,
                "placar_b": confronto.placar_b,
            }
            for confronto in resultado.confrontos
        ]

        stmt = pg_insert(AgendaPartida).values(linhas)
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_agenda_jogo_externo",
                set_={
                    # O horario muda (adiamento) e o placar nasce nulo e depois
                    # existe - por isso o upsert atualiza em vez de ignorar: a
                    # linha coletada como "por vir" precisa virar resultado na
                    # rodada seguinte, no lugar, sem duplicar o confronto.
                    "inicio_previsto": stmt.excluded.inicio_previsto,
                    "torneio": stmt.excluded.torneio,
                    "formato": stmt.excluded.formato,
                    "id_equipe_a": stmt.excluded.id_equipe_a,
                    "id_equipe_b": stmt.excluded.id_equipe_b,
                    "coletado_em": stmt.excluded.coletado_em,
                    "vitoria_a": stmt.excluded.vitoria_a,
                    "placar_a": stmt.excluded.placar_a,
                    "placar_b": stmt.excluded.placar_b,
                },
            )
        )

    logger.info(
        "confrontos de lol carregados",
        extra={"equipes": len(resultado.equipes), "confrontos": len(linhas)},
    )
    return len(linhas)
