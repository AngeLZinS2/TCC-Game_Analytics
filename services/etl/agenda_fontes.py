"""Precedência de fonte em `agenda_partida`.

A mesma partida entra por mais de uma fonte — Liquipedia e OP.GG (id em hash,
sem prefixo), vlr.gg/hltv (`vlr:`/`hltv:`), PandaScore (`pandascore:`) — com
nome e horário diferentes. Sem cortar, a lista de confrontos mostra a partida
2x e o modelo de Bradley-Terry conta o resultado 2x.

A regra: a primeira fonte da lista que tenha linha ganha, e as outras somem —
para aquele jogo, ou para aquele recorte.

**vlr.gg antes da PandaScore de propósito**: o `vlr:` só existe para Valorant, e
é a linha `vlr` que carrega o `detalhe` por mapa (`vlr_detalhes`). Se a
PandaScore ganhasse, o botão "por mapa" sumia. A PandaScore de Valorant entra
só pelo escudo dos times (backfill no `carregar_agenda`). Para CS, `hltv:` fica
DEPOIS da PandaScore — senão linha `hltv` velha (pré-migração) ressuscitava e
escondia a PandaScore.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.models import AgendaPartida, DimJogo

#: Ordem de preferência. Quem não casa com nenhuma cláusula é o resto
#: (Liquipedia, OP.GG) — só entra quando ninguém acima tem linha.
_PRECEDENCIA = (
    AgendaPartida.id_externo.op("~")("^vlr:"),
    AgendaPartida.id_externo.op("~")("^pandascore:"),
    AgendaPartida.id_externo.op("~")("^hltv:"),
)


def restringir_recorte(sessao: Session, base_select):
    """Restringe `base_select` à fonte preferida com linha DENTRO do recorte.

    Para os endpoints: se só há linha de fonte dedicada para a agenda e não
    para os resultados, os resultados continuam vindo da Liquipedia.
    """
    for clausula in _PRECEDENCIA:
        tem = sessao.scalar(
            select(func.count()).select_from(
                base_select.where(clausula).subquery()
            )
        )
        if tem:
            return base_select.where(clausula)
    return base_select


def clausula_para_jogo(sessao: Session, jogo_codigo: str):
    """A cláusula WHERE da fonte preferida para os confrontos DECIDIDOS de um
    jogo, ou `None` quando não há fonte dedicada (usa tudo).

    Para o modelo de confronto: aplicar a mesma cláusula a toda leitura de
    `agenda_partida` daquele jogo mantém a contagem coerente.
    """
    for clausula in _PRECEDENCIA:
        tem = sessao.scalar(
            select(func.count())
            .select_from(AgendaPartida)
            .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
            .where(
                DimJogo.codigo == jogo_codigo,
                AgendaPartida.vitoria_a.is_not(None),
                clausula,
            )
        )
        if tem:
            return clausula
    return None
