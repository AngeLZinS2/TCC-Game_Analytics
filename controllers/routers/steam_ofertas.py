"""Ofertas (promocoes ativas) do catalogo Steam - Fase 35.

Le so do Postgres - nunca chama a Steam ao vivo. `steam_promocoes` e
alimentada por `load_steam_precos.py`, uma transicao real de desconto por
app, nunca por heuristica de catalogo. Mesmo prefixo/estilo do router
`steam.py` (arquivo separado so por organizacao).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from models.models import DimJogoSteam, PromocaoSteam
from models.session import get_db
from views.schemas import OfertaSteam

router = APIRouter(prefix="/api/steam", tags=["steam"])

OrdenarOfertaPor = Literal["desconto_desc", "preco_asc"]


@router.get("/ofertas", response_model=list[OfertaSteam])
def listar_ofertas(
    sessao: Session = Depends(get_db),
    desconto_minimo: int = Query(0, ge=0, le=100),
    preco_maximo: Decimal | None = Query(None, ge=0),
    pais: str | None = Query(None, min_length=2, max_length=2),
    moeda: str | None = Query(None, min_length=1, max_length=8),
    ordenar_por: OrdenarOfertaPor = "desconto_desc",
    limite: int = Query(50, ge=1, le=200),
) -> list[OfertaSteam]:
    """Promocoes ABERTAS agora, primeiro-partido (nao ITAD).

    Sem "upcoming": a Steam nao expoe data de inicio de promocao futura, so
    o que ja esta em desconto observado.
    """
    consulta = (
        select(PromocaoSteam, DimJogoSteam)
        .join(DimJogoSteam, DimJogoSteam.app_id == PromocaoSteam.app_id)
        .where(
            PromocaoSteam.ativa.is_(True),
            PromocaoSteam.desconto_percentual >= desconto_minimo,
        )
    )
    if pais:
        consulta = consulta.where(PromocaoSteam.pais == pais.upper())
    if moeda:
        consulta = consulta.where(PromocaoSteam.moeda == moeda.upper())
    if preco_maximo is not None:
        consulta = consulta.where(
            PromocaoSteam.preco_final <= int((preco_maximo * 100).to_integral_value())
        )

    if ordenar_por == "preco_asc":
        consulta = consulta.order_by(PromocaoSteam.preco_final.asc())
    else:
        consulta = consulta.order_by(
            desc(PromocaoSteam.desconto_percentual), PromocaoSteam.preco_final.asc()
        )
    consulta = consulta.limit(limite)

    return [
        OfertaSteam(
            app_id=promocao.app_id,
            nome=jogo.nome,
            imagem_header=jogo.imagem_header,
            preco_original=Decimal(promocao.preco_original) / 100,
            preco_final=Decimal(promocao.preco_final) / 100,
            desconto_percentual=promocao.desconto_percentual,
            moeda=promocao.moeda,
            pais=promocao.pais,
            iniciada_em=promocao.iniciada_em,
        )
        for promocao, jogo in sessao.execute(consulta)
    ]
