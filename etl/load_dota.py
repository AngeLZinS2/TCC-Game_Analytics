"""Carga do dominio de partidas (Dota 2) no PostgreSQL.

A ordem importa: dim_tempo -> dim_personagem -> dim_jogador -> dim_partida ->
fato_partida_jogador. As dimensoes precisam existir antes do fato porque e
delas que saem as chaves substitutas.

Idempotencia por chave natural em todos os niveis:
  dim_personagem  (id_jogo, id_externo)
  dim_jogador     (id_jogo, id_externo)
  dim_equipe      (id_jogo, id_externo)
  dim_partida     (id_jogo, id_externo)
  fato_jogador    (id_partida, slot)
  fato_minuto     (id_partida, minuto)
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models import (
    DimEquipe,
    DimJogador,
    DimJogo,
    DimPartida,
    DimPersonagem,
    FatoMinutoPartida,
    FatoPartidaJogador,
)
from db.session import session_scope
from etl.dim_tempo import garantir_dim_tempo
from etl.lotes import em_lotes
from etl.transform_dota import JOGO, ResultadoDota

logger = logging.getLogger(__name__)


class JogoNaoCadastradoError(RuntimeError):
    """dim_jogo e semeada pela migration 0002; sem ela nada pode ser carregado."""


def _id_do_jogo(sessao: Session, codigo: str = JOGO) -> int:
    id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == codigo))
    if id_jogo is None:
        raise JogoNaoCadastradoError(
            f"jogo {codigo!r} ausente em dim_jogo - rode as migrations (cli.py init-db)"
        )
    return id_jogo


def _upsert_dimensao(
    sessao: Session,
    modelo: type,
    linhas: list[dict[str, Any]],
    restricao: str,
    atualizaveis: tuple[str, ...],
) -> int:
    """Upsert generico de dimensao por (id_jogo, id_externo)."""
    if not linhas:
        return 0

    stmt = pg_insert(modelo).values(linhas)
    stmt = stmt.on_conflict_do_update(
        constraint=restricao,
        set_={coluna: stmt.excluded[coluna] for coluna in atualizaveis},
    )
    sessao.execute(stmt)
    return len(linhas)


def _mapa_externo_para_id(
    sessao: Session, modelo: type, coluna_id: Any, id_jogo: int
) -> dict[str, int]:
    """id_externo -> chave substituta, para resolver as FKs do fato."""
    linhas = sessao.execute(
        select(modelo.id_externo, coluna_id).where(modelo.id_jogo == id_jogo)
    ).all()
    return {id_externo: chave for id_externo, chave in linhas}


def carregar(resultado: ResultadoDota) -> int:
    """Persiste dimensoes e fato numa unica transacao."""
    with session_scope() as sessao:
        id_jogo = _id_do_jogo(sessao)

        chaves_tempo = [p.id_tempo for p in resultado.partidas]
        chaves_tempo += [p.id_tempo for p in resultado.participacoes]
        garantir_dim_tempo(sessao, chaves_tempo)

        personagens = _upsert_dimensao(
            sessao,
            DimPersonagem,
            [
                {"id_jogo": id_jogo, **p.model_dump()}
                for p in resultado.personagens
            ],
            "uq_personagem_jogo_externo",
            ("nome", "nome_interno"),
        )
        jogadores = _upsert_dimensao(
            sessao,
            DimJogador,
            [{"id_jogo": id_jogo, **j.model_dump()} for j in resultado.jogadores],
            "uq_jogador_jogo_externo",
            ("nome", "regiao"),
        )
        equipes = _upsert_dimensao(
            sessao,
            DimEquipe,
            [{"id_jogo": id_jogo, **e.model_dump()} for e in resultado.equipes],
            "uq_equipe_jogo_externo",
            ("nome", "tag", "logo_url"),
        )
        sessao.flush()
        mapa_equipe = _mapa_externo_para_id(sessao, DimEquipe, DimEquipe.id_equipe, id_jogo)

        linhas_partida = []
        for partida in resultado.partidas:
            linha = partida.model_dump(
                exclude={"equipe_lado_a_externo", "equipe_lado_b_externo"}
            )
            linha["id_jogo"] = id_jogo
            linha["id_equipe_lado_a"] = mapa_equipe.get(partida.equipe_lado_a_externo or "")
            linha["id_equipe_lado_b"] = mapa_equipe.get(partida.equipe_lado_b_externo or "")
            linhas_partida.append(linha)

        partidas = _upsert_dimensao(
            sessao,
            DimPartida,
            linhas_partida,
            "uq_partida_jogo_externo",
            (
                "data_inicio",
                "id_tempo",
                "duracao_segundos",
                "modo",
                "tipo_partida",
                "patch",
                "liga_nome",
                "liga_id_externo",
                "liga_tier",
                "id_equipe_lado_a",
                "id_equipe_lado_b",
            ),
        )
        sessao.flush()

        mapa_partida = _mapa_externo_para_id(
            sessao, DimPartida, DimPartida.id_partida, id_jogo
        )
        mapa_jogador = _mapa_externo_para_id(
            sessao, DimJogador, DimJogador.id_jogador, id_jogo
        )
        mapa_personagem = _mapa_externo_para_id(
            sessao, DimPersonagem, DimPersonagem.id_personagem, id_jogo
        )

        fatos: list[dict[str, Any]] = []
        for participacao in resultado.participacoes:
            id_partida = mapa_partida.get(participacao.id_partida_externo)
            if id_partida is None:
                # So acontece se a dimensao foi descartada no transform.
                continue

            linha = participacao.model_dump(
                exclude={
                    "id_partida_externo",
                    "id_jogador_externo",
                    "id_personagem_externo",
                }
            )
            linha["id_partida"] = id_partida
            linha["id_jogo"] = id_jogo
            linha["id_jogador"] = mapa_jogador.get(participacao.id_jogador_externo or "")
            linha["id_personagem"] = mapa_personagem.get(
                participacao.id_personagem_externo or ""
            )
            fatos.append(linha)

        carregados = _upsert_fato(sessao, fatos)

        minutos_linhas: list[dict[str, Any]] = []
        for minuto in resultado.minutos:
            id_partida = mapa_partida.get(minuto.id_partida_externo)
            if id_partida is None:
                continue
            linha = minuto.model_dump(exclude={"id_partida_externo"})
            linha["id_partida"] = id_partida
            linha["id_jogo"] = id_jogo
            minutos_linhas.append(linha)

        minutos = _upsert_minutos(sessao, minutos_linhas)

    logger.info(
        "carga dota concluida",
        extra={
            "personagens": personagens,
            "jogadores": jogadores,
            "equipes": equipes,
            "partidas": partidas,
            "participacoes": carregados,
            "minutos": minutos,
        },
    )
    return personagens + jogadores + equipes + partidas + carregados + minutos


def _upsert_fato(sessao: Session, fatos: list[dict[str, Any]]) -> int:
    if not fatos:
        return 0

    for lote in em_lotes(fatos):
        stmt = pg_insert(FatoPartidaJogador).values(lote)
        atualizaveis = {
            coluna: stmt.excluded[coluna]
            for coluna in lote[0]
            if coluna not in ("id_partida", "slot")
        }
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_fato_partida_slot", set_=atualizaveis
            )
        )

    return len(fatos)


def _upsert_minutos(sessao: Session, linhas: list[dict[str, Any]]) -> int:
    """Idempotente por (id_partida, minuto).

    Reprocessar o mesmo payload reescreve a linha em vez de duplicar - e o que
    permite rodar `collect dota --from-raw` quantas vezes for preciso quando o
    calculo das features mudar.
    """
    if not linhas:
        return 0

    for lote in em_lotes(linhas):
        stmt = pg_insert(FatoMinutoPartida).values(lote)
        atualizaveis = {
            coluna: stmt.excluded[coluna]
            for coluna in lote[0]
            if coluna not in ("id_partida", "minuto")
        }
        sessao.execute(
            stmt.on_conflict_do_update(
                constraint="uq_minuto_partida", set_=atualizaveis
            )
        )

    return len(linhas)
