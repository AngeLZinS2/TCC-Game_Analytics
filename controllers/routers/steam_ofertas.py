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
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from models.models import DimJogoSteam, PromocaoSteam
from models.session import get_db
from views.schemas import OfertaSteam, PaginaOfertasSteam

router = APIRouter(prefix="/api/steam", tags=["steam"])

OrdenarOfertaPor = Literal["desconto_desc", "preco_asc"]


@router.get("/ofertas", response_model=PaginaOfertasSteam)
def listar_ofertas(
    sessao: Session = Depends(get_db),
    busca: str | None = Query(None, min_length=1, max_length=100),
    desconto_minimo: int = Query(0, ge=0, le=100),
    preco_maximo: Decimal | None = Query(None, ge=0),
    pais: str | None = Query(None, min_length=2, max_length=2),
    moeda: str | None = Query(None, min_length=1, max_length=8),
    ordenar_por: OrdenarOfertaPor = "desconto_desc",
    limite: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginaOfertasSteam:
    """Promocoes ABERTAS agora, primeiro-partido (nao ITAD).

    Sem "upcoming": a Steam nao expoe data de inicio de promocao futura, so
    o que ja esta em desconto observado. Paginado (Fase 35.1) - a varredura
    completa de ofertas fez o catalogo crescer de dezenas pra ~20 mil linhas,
    grande demais pra mandar tudo de uma vez pro navegador.
    """
    condicoes = [
        PromocaoSteam.ativa.is_(True),
        PromocaoSteam.desconto_percentual >= desconto_minimo,
    ]
    if busca:
        condicoes.append(DimJogoSteam.nome.ilike(f"%{busca}%"))
    if pais:
        condicoes.append(PromocaoSteam.pais == pais.upper())
    if moeda:
        condicoes.append(PromocaoSteam.moeda == moeda.upper())
    if preco_maximo is not None:
        condicoes.append(
            PromocaoSteam.preco_final <= int((preco_maximo * 100).to_integral_value())
        )

    base = (
        select(PromocaoSteam, DimJogoSteam)
        .join(DimJogoSteam, DimJogoSteam.app_id == PromocaoSteam.app_id)
        .where(*condicoes)
    )

    total = sessao.scalar(
        select(func.count()).select_from(base.with_only_columns(PromocaoSteam.app_id).subquery())
    ) or 0

    if ordenar_por == "preco_asc":
        base = base.order_by(PromocaoSteam.preco_final.asc())
    else:
        base = base.order_by(
            desc(PromocaoSteam.desconto_percentual), PromocaoSteam.preco_final.asc()
        )
    base = base.limit(limite).offset(offset)

    itens = [
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
        for promocao, jogo in sessao.execute(base)
    ]
    return PaginaOfertasSteam(itens=itens, total=total)
