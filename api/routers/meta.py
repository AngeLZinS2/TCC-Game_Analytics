"""Endpoint transversal: os numeros que abrem o dashboard.

Atravessa os dois dominios de proposito - e a unica rota que faz isso. Todo o
resto da API respeita a separacao entre catalogo/mercado e partidas.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from api.schemas import ColetaFonte, VisaoGeral
from db.models import (
    DimJogador,
    DimJogoSteam,
    DimPartida,
    DimPersonagem,
    FatoPartidaJogador,
    FatoSnapshotJogoSteam,
    RawData,
)
from db.session import get_db

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/visao-geral", response_model=VisaoGeral)
def visao_geral(sessao: Session = Depends(get_db)) -> VisaoGeral:
    """Contagens por dominio + quando cada fonte foi coletada pela ultima vez."""

    def contar(modelo) -> int:
        return sessao.scalar(select(func.count()).select_from(modelo)) or 0

    # Soma dos jogadores simultaneos considerando so o snapshot mais recente de
    # cada jogo - somar a serie inteira contaria a mesma populacao varias vezes.
    ultimo = (
        select(FatoSnapshotJogoSteam.jogadores_simultaneos.label("jogadores"))
        .distinct(FatoSnapshotJogoSteam.app_id)
        .order_by(
            FatoSnapshotJogoSteam.app_id,
            desc(FatoSnapshotJogoSteam.janela_coleta),
        )
        .subquery()
    )
    jogadores_simultaneos = sessao.scalar(select(func.sum(ultimo.c.jogadores)))

    coletas = sessao.execute(
        select(
            RawData.fonte,
            func.count().label("payloads"),
            func.max(RawData.coletado_em).label("ultima"),
        )
        .group_by(RawData.fonte)
        .order_by(RawData.fonte)
    ).all()

    return VisaoGeral(
        jogos_steam=contar(DimJogoSteam),
        snapshots_steam=contar(FatoSnapshotJogoSteam),
        jogadores_simultaneos_total=(
            int(jogadores_simultaneos) if jogadores_simultaneos is not None else None
        ),
        partidas=contar(DimPartida),
        linhas_fato_partida=contar(FatoPartidaJogador),
        jogadores=contar(DimJogador),
        personagens=contar(DimPersonagem),
        coletas=[
            ColetaFonte(
                fonte=linha.fonte, payloads=linha.payloads, ultima_coleta=linha.ultima
            )
            for linha in coletas
        ],
    )
