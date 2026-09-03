"""Endpoints do dominio catalogo/mercado (Steam).

A tabela de fato tem uma linha por (app_id, janela_coleta). Quase toda tela do
dashboard quer "o estado agora", que e o snapshot mais recente de cada jogo -
por isso o DISTINCT ON aparece em varios lugares aqui.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, desc, func, nulls_last, or_, select
from sqlalchemy.orm import Session, aliased

from api.schemas import (
    AgregadoGenero,
    DetalheJogoSteam,
    JogoSteam,
    PontoSerie,
    PontoSerieTotal,
)
from db.models import DimJogoSteam, FatoSnapshotJogoSteam
from db.session import get_db

router = APIRouter(prefix="/api/steam", tags=["steam"])

OrdenarPor = Literal[
    "jogadores", "avaliacoes", "numero_avaliacoes", "preco", "metacritic", "nome"
]


def _ultimo_snapshot():
    """Alias ORM do snapshot mais recente de cada app_id (DISTINCT ON)."""
    subconsulta = (
        select(FatoSnapshotJogoSteam)
        .distinct(FatoSnapshotJogoSteam.app_id)
        .order_by(
            FatoSnapshotJogoSteam.app_id,
            desc(FatoSnapshotJogoSteam.janela_coleta),
        )
        .subquery()
    )
    return aliased(FatoSnapshotJogoSteam, subconsulta), subconsulta


def _estatisticas_por_app():
    """Pico historico e o valor da coleta ANTERIOR, por app_id.

    O `_ultimo_snapshot` responde "quanto e agora". Estas duas colunas respondem
    "quanto ja foi" e "quanto era antes" - e sem a segunda nao existe variacao
    para mostrar, so um numero solto sem referencia.

    A janela numerada resolve as duas de uma vez: posicao 1 e a coleta atual,
    posicao 2 e a anterior. Duas subconsultas separadas varreriam o fato duas
    vezes para chegar no mesmo lugar.
    """
    numerado = select(
        FatoSnapshotJogoSteam.app_id,
        FatoSnapshotJogoSteam.jogadores_simultaneos,
        func.row_number()
        .over(
            partition_by=FatoSnapshotJogoSteam.app_id,
            order_by=desc(FatoSnapshotJogoSteam.janela_coleta),
        )
        .label("posicao"),
    ).subquery()

    return (
        select(
            numerado.c.app_id.label("app_id"),
            func.max(numerado.c.jogadores_simultaneos).label("pico"),
            func.max(
                case((numerado.c.posicao == 2, numerado.c.jogadores_simultaneos))
            ).label("anterior"),
        )
        .group_by(numerado.c.app_id)
        .subquery()
    )


def _variacao(atual: int | None, anterior: int | None) -> float | None:
    """Variacao percentual entre duas coletas.

    None quando nao ha com o que comparar - e o caso de todo jogo enquanto so
    existir uma coleta. Devolver 0 ali seria afirmar "nao mudou", que e
    diferente de "ainda nao da para saber".
    """
    if atual is None or not anterior:
        return None
    return round((atual - anterior) / anterior * 100, 2)


def _montar_jogo(
    jogo: DimJogoSteam,
    snap: FatoSnapshotJogoSteam | None,
    pico: int | None = None,
    anterior: int | None = None,
) -> JogoSteam:
    """Achata dimensao + fato na linha que a tabela do dashboard consome."""
    return JogoSteam(
        app_id=jogo.app_id,
        nome=jogo.nome,
        desenvolvedora=jogo.desenvolvedora,
        publicadora=jogo.publicadora,
        data_lancamento=jogo.data_lancamento,
        generos=jogo.generos or [],
        gratuito=jogo.gratuito,
        nota_metacritic=jogo.nota_metacritic,
        janela_coleta=snap.janela_coleta if snap else None,
        jogadores_simultaneos=snap.jogadores_simultaneos if snap else None,
        nota_avaliacoes=snap.nota_avaliacoes if snap else None,
        numero_avaliacoes=snap.numero_avaliacoes if snap else None,
        classificacao_steam=snap.classificacao_steam if snap else None,
        preco_no_momento=snap.preco_no_momento if snap else None,
        moeda=snap.moeda if snap else None,
        desconto_percentual=snap.desconto_percentual if snap else None,
        pico_jogadores=pico,
        variacao_jogadores=_variacao(
            snap.jogadores_simultaneos if snap else None, anterior
        ),
    )


@router.get("/jogos", response_model=list[JogoSteam])
def listar_jogos(
    sessao: Session = Depends(get_db),
    busca: str | None = Query(None, description="filtra por nome ou desenvolvedora"),
    genero: str | None = Query(None, description="filtra por um genero exato"),
    ordenar_por: OrdenarPor = "jogadores",
    ordem: Literal["asc", "desc"] = "desc",
    limite: int = Query(100, ge=1, le=500),
) -> list[JogoSteam]:
    """Catalogo monitorado, cada jogo com seu snapshot mais recente."""
    snap, _ = _ultimo_snapshot()

    ordenacoes = {
        "jogadores": snap.jogadores_simultaneos,
        "avaliacoes": snap.nota_avaliacoes,
        "numero_avaliacoes": snap.numero_avaliacoes,
        "preco": snap.preco_no_momento,
        "metacritic": DimJogoSteam.nota_metacritic,
        "nome": DimJogoSteam.nome,
    }

    estatisticas = _estatisticas_por_app()

    consulta = (
        select(DimJogoSteam, snap, estatisticas.c.pico, estatisticas.c.anterior)
        .outerjoin(snap, snap.app_id == DimJogoSteam.app_id)
        .outerjoin(estatisticas, estatisticas.c.app_id == DimJogoSteam.app_id)
    )

    if busca:
        padrao = f"%{busca}%"
        consulta = consulta.where(
            or_(
                DimJogoSteam.nome.ilike(padrao),
                DimJogoSteam.desenvolvedora.ilike(padrao),
            )
        )
    if genero:
        consulta = consulta.where(DimJogoSteam.generos.any(genero))

    coluna = ordenacoes[ordenar_por]
    alvo = desc(coluna) if ordem == "desc" else coluna.asc()
    # nulls_last nas duas direcoes: jogo sem snapshot nunca lidera o ranking.
    consulta = consulta.order_by(nulls_last(alvo)).limit(limite)

    return [
        _montar_jogo(jogo, snapshot, pico, anterior)
        for jogo, snapshot, pico, anterior in sessao.execute(consulta)
    ]


@router.get("/generos", response_model=list[AgregadoGenero])
def agregar_por_genero(sessao: Session = Depends(get_db)) -> list[AgregadoGenero]:
    """Um jogo conta em todos os seus generos - a soma passa do total de jogos."""
    snap, _ = _ultimo_snapshot()
    genero = func.unnest(DimJogoSteam.generos).label("genero")

    consulta = (
        select(
            genero,
            func.count(func.distinct(DimJogoSteam.app_id)).label("jogos"),
            func.sum(snap.jogadores_simultaneos).label("jogadores"),
            func.avg(snap.nota_avaliacoes).label("nota"),
        )
        .outerjoin(snap, snap.app_id == DimJogoSteam.app_id)
        .group_by(genero)
        .order_by(nulls_last(desc("jogadores")))
    )

    return [
        AgregadoGenero(
            genero=linha.genero,
            jogos=linha.jogos,
            jogadores_simultaneos=linha.jogadores,
            nota_avaliacoes_media=linha.nota,
        )
        for linha in sessao.execute(consulta)
    ]


@router.get("/jogos/{app_id}", response_model=DetalheJogoSteam)
def detalhar_jogo(app_id: int, sessao: Session = Depends(get_db)) -> DetalheJogoSteam:
    """Jogo + toda a serie temporal ja coletada dele."""
    jogo = sessao.get(DimJogoSteam, app_id)
    if jogo is None:
        raise HTTPException(status_code=404, detail=f"app_id {app_id} nao monitorado")

    snapshots = list(
        sessao.scalars(
            select(FatoSnapshotJogoSteam)
            .where(FatoSnapshotJogoSteam.app_id == app_id)
            .order_by(FatoSnapshotJogoSteam.janela_coleta)
        )
    )

    return DetalheJogoSteam(
        jogo=_montar_jogo(
            jogo,
            snapshots[-1] if snapshots else None,
            pico=max(
                (s.jogadores_simultaneos for s in snapshots if s.jogadores_simultaneos),
                default=None,
            ),
            anterior=(
                snapshots[-2].jogadores_simultaneos if len(snapshots) > 1 else None
            ),
        ),
        serie=[
            PontoSerie(
                janela_coleta=s.janela_coleta,
                jogadores_simultaneos=s.jogadores_simultaneos,
                nota_avaliacoes=s.nota_avaliacoes,
                numero_avaliacoes=s.numero_avaliacoes,
                preco_no_momento=s.preco_no_momento,
                desconto_percentual=s.desconto_percentual,
            )
            for s in snapshots
        ],
    )


@router.get("/serie-total", response_model=list[PontoSerieTotal])
def serie_total(sessao: Session = Depends(get_db)) -> list[PontoSerieTotal]:
    """Jogadores simultaneos somados sobre todo o catalogo, por janela de coleta.

    E a serie que o sparkline do KPI desenha. Somar no banco e nao no navegador
    importa porque a alternativa seria baixar a serie inteira de cada jogo so
    para reduzi-la a um numero por janela.
    """
    consulta = (
        select(
            FatoSnapshotJogoSteam.janela_coleta.label("janela_coleta"),
            func.sum(FatoSnapshotJogoSteam.jogadores_simultaneos).label("jogadores"),
            func.count(func.distinct(FatoSnapshotJogoSteam.app_id)).label("jogos"),
        )
        .group_by(FatoSnapshotJogoSteam.janela_coleta)
        .order_by(FatoSnapshotJogoSteam.janela_coleta)
    )
    return [
        PontoSerieTotal(janela_coleta=janela, jogadores_simultaneos=jogadores, jogos=jogos)
        for janela, jogadores, jogos in sessao.execute(consulta)
    ]
