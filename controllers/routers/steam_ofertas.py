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

from models.models import DimJogoSteam, DimTagSteam, PromocaoSteam
from models.session import get_db
from views.schemas import OfertaSteam, PaginaOfertasSteam, TagOfertaSteam

router = APIRouter(prefix="/api/steam", tags=["steam"])

OrdenarOfertaPor = Literal["nome_asc", "desconto_desc", "preco_asc"]

#: A lista de Ofertas mostra JOGO, e so. A varredura tambem traz DLC
#: (`category1=21`), porque a promocao dela importa - mas o lugar dela e a
#: ficha do jogo dono, nao uma vitrine onde "Pack de Temporada 2026" disputa
#: espaco com o jogo. Trilha sonora, video e software nem sao mais varridos.
#:
#: E `tipo == "game"` e nao `tipo != "dlc"` de proposito: mostrar so o que
#: sabemos ser jogo e mais honesto do que mostrar tudo que ainda nao
#: provamos ser DLC. O preco disso e que app sem `tipo` (varredura antiga,
#: antes de 2026-09-16) fica de fora ate a proxima varredura preencher.
TIPO_JOGO = "game"

#: Os ids de tag que a Steam usa como GENERO de loja (as paginas
#: `store.steampowered.com/genre/...`), conferidos contra o dicionario vivo
#: em `/tagdata/populartags`. Tudo que nao esta aqui e caracteristica ou tema
#: ("Um Jogador", "Co-op", "Atmosferico"), e vira o filtro de "categoria".
#:
#: E uma lista curada porque a Steam nao marca, no HTML da busca nem no
#: dicionario, qual tag e genero - so o id e estavel o bastante para isso
#: (o nome muda com o idioma da coleta).
TAGS_DE_GENERO: frozenset[int] = frozenset(
    {
        19,  # Acao
        21,  # Aventura
        122,  # RPG
        9,  # Estrategia
        599,  # Simulacao
        701,  # Esportes
        699,  # Corrida
        492,  # Indie
        597,  # Casual
        128,  # Multijogador Massivo
        493,  # Acesso Antecipado
        113,  # Gratuito para Jogar
        1667,  # Terror
        1625,  # Plataforma
        1743,  # Luta
        1774,  # Tiro
        1628,  # Metroidvania
    }
)


@router.get("/ofertas", response_model=PaginaOfertasSteam)
def listar_ofertas(
    sessao: Session = Depends(get_db),
    busca: str | None = Query(None, min_length=1, max_length=100),
    desconto_minimo: int = Query(0, ge=0, le=100),
    preco_maximo: Decimal | None = Query(None, ge=0),
    pais: str | None = Query(None, min_length=2, max_length=2),
    moeda: str | None = Query(None, min_length=1, max_length=8),
    tag: int | None = Query(None, description="id de tag da Steam (genero/categoria)"),
    categoria: int | None = Query(None, description="id de tag de caracteristica/tema"),
    ordenar_por: OrdenarOfertaPor = "nome_asc",
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
        DimJogoSteam.tipo == TIPO_JOGO,
    ]
    if busca:
        condicoes.append(DimJogoSteam.nome.ilike(f"%{busca}%"))
    # `tag` e `categoria` sao a MESMA coluna - o que muda e de qual dropdown
    # o id veio (ver `TAGS_DE_GENERO`). Passar os dois filtra por ambos, que
    # e o comportamento esperado de dois filtros combinados.
    for id_tag in (tag, categoria):
        if id_tag is not None:
            condicoes.append(DimJogoSteam.tags_steam.any(id_tag))
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
    elif ordenar_por == "desconto_desc":
        base = base.order_by(
            desc(PromocaoSteam.desconto_percentual), PromocaoSteam.preco_final.asc()
        )
    else:
        # Alfabetica de verdade: `collate "C"` ordenaria por byte e jogaria
        # todo titulo com acento ou minuscula pro fim da lista. Sem isso,
        # "Ámbar" nao cairia perto de "Amnesia" e a ordem pareceria quebrada
        # pra quem le em portugues.
        base = base.order_by(func.lower(DimJogoSteam.nome).asc(), DimJogoSteam.app_id.asc())
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


@router.get("/ofertas/tags", response_model=list[TagOfertaSteam])
def tags_das_ofertas(
    sessao: Session = Depends(get_db),
    minimo: int = Query(5, ge=1, description="descarta tag com menos ofertas que isso"),
) -> list[TagOfertaSteam]:
    """As tags presentes nas ofertas ABERTAS agora, com a contagem de cada uma.

    Popula os dois dropdowns da tela de Ofertas. So entra tag que existe nas
    ofertas de agora - um dropdown com as 429 tags do dicionario, a maioria
    sem nenhuma oferta atras, seria uma lista de becos sem saida.

    `minimo` corta a cauda longa (tags com duas ou tres ofertas), que enche o
    dropdown sem ajudar a achar nada.
    """
    tag_id = func.unnest(DimJogoSteam.tags_steam).label("tag_id")
    por_tag = (
        select(tag_id, func.count().label("ofertas"))
        .select_from(PromocaoSteam)
        .join(DimJogoSteam, DimJogoSteam.app_id == PromocaoSteam.app_id)
        .where(
            PromocaoSteam.ativa.is_(True),
            DimJogoSteam.tags_steam.is_not(None),
            # Mesmo universo da listagem: um dropdown que promete 40 ofertas
            # de "Corrida" e entrega 12 porque 28 eram DLC esta mentindo.
            DimJogoSteam.tipo == TIPO_JOGO,
        )
        .group_by(tag_id)
        .subquery()
    )

    consulta = (
        select(por_tag.c.tag_id, por_tag.c.ofertas, DimTagSteam.nome)
        .join(DimTagSteam, DimTagSteam.tag_id == por_tag.c.tag_id)
        .where(por_tag.c.ofertas >= minimo)
        .order_by(desc(por_tag.c.ofertas))
    )

    return [
        TagOfertaSteam(
            tag_id=id_tag,
            nome=nome,
            ofertas=ofertas,
            genero=id_tag in TAGS_DE_GENERO,
        )
        for id_tag, ofertas, nome in sessao.execute(consulta)
    ]
