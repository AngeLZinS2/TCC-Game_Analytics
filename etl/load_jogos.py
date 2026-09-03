"""Sincroniza `dim_jogo` com o registro de wikis da Liquipedia.

A migration `0002` semeou tres jogos a mao. Com 73 wikis isso deixou de caber
numa migration: a lista muda quando a Liquipedia abre uma wiki nova, e uma
migration e um registro historico - reescreve-la para acrescentar um jogo seria
mentir sobre o que aconteceu naquele dia.

Por isso a sincronizacao vive aqui e roda por comando. E idempotente: rodar duas
vezes nao duplica, e um jogo que sai do registro **nao e apagado**, porque pode
haver partida apontando para ele. Sumir com a dimensao deixaria fato orfao.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from db.models import DimJogo
from db.session import session_scope
from etl.wikis import registro

logger = logging.getLogger(__name__)


def sincronizar() -> int:
    """Garante uma linha em `dim_jogo` por wiki. Devolve quantas foram criadas."""
    with session_scope() as sessao:
        existentes = {
            codigo: nome
            for codigo, nome in sessao.execute(
                select(DimJogo.codigo, DimJogo.nome)
            )
        }

        criados = renomeados = 0
        for wiki in registro():
            if wiki.codigo not in existentes:
                sessao.add(DimJogo(codigo=wiki.codigo, nome=wiki.nome))
                criados += 1
                continue

            # O nome pode ter mudado na fonte ("Valorant" -> "VALORANT").
            if existentes[wiki.codigo] != wiki.nome:
                jogo = sessao.scalar(
                    select(DimJogo).where(DimJogo.codigo == wiki.codigo)
                )
                if jogo is not None:
                    jogo.nome = wiki.nome
                    renomeados += 1

        logger.info(
            "dim_jogo sincronizada",
            extra={
                "no_registro": len(registro()),
                "criados": criados,
                "renomeados": renomeados,
                "ja_existiam": len(existentes),
            },
        )
        return criados
