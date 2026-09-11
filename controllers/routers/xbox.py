"""Endpoints da vitrine Xbox (aba "Xbox" do Catalogo de Jogos).

Mesmo desenho do `steam.py`: a tabela de fato tem uma linha por
`(product_id, janela_coleta)` e quase toda tela quer "o estado agora", entao o
DISTINCT ON do snapshot mais recente aparece nas duas listagens.

Raso de proposito - a fonte da Microsoft nao publica CCU nem avaliacao. O que
a vitrine mostra e ficha + preco + o selo do Game Pass.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, desc, func, nulls_last, or_, select
from sqlalchemy.orm import Session, aliased

from views.schemas import (
    AgregadoGenero,
    CandidatoJogoXbox,
    DetalheJogoXbox,
    EntradaColetaXbox,
    JogoXbox,
    PontoSerieXbox,
    ResumoColetaXbox,
)
from config import get_settings
from models.models import DimJogoXbox, FatoSnapshotJogoXbox
from models.session import get_db, session_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/xbox", tags=["xbox"])

OrdenarPor = Literal["game_pass", "nome", "preco", "lancamento", "nota"]

#: Abaixo disto, a nota da Store diz mais sobre o tamanho da amostra do que
#: sobre o jogo - fica fora do topo do ranking "melhor avaliados".
_MINIMO_AVALIACOES_RANKING = 20


def _ultimo_snapshot():
    """Alias ORM do snapshot mais recente de cada product_id (DISTINCT ON)."""
    subconsulta = (
        select(FatoSnapshotJogoXbox)
        .distinct(FatoSnapshotJogoXbox.product_id)
        .order_by(
            FatoSnapshotJogoXbox.product_id,
            desc(FatoSnapshotJogoXbox.janela_coleta),
        )
        .subquery()
    )
    return aliased(FatoSnapshotJogoXbox, subconsulta), subconsulta


def _montar_jogo(
    jogo: DimJogoXbox, snap: FatoSnapshotJogoXbox | None
) -> JogoXbox:
    """Achata dimensao + snapshot na linha que a vitrine consome.

    O preco sai do snapshot quando ha um; senao cai para o que ficou gravado na
    dimensao (`preco_atual`) - assim um jogo recem-coletado, ainda sem serie,
    ja mostra preco.
    """
    return JogoXbox(
        product_id=jogo.product_id,
        nome=jogo.nome,
        tipo=jogo.tipo,
        desenvolvedora=jogo.desenvolvedora,
        publicadora=jogo.publicadora,
        data_lancamento=jogo.data_lancamento,
        generos=jogo.generos or [],
        gratuito=jogo.gratuito,
        faixa_etaria=jogo.faixa_etaria,
        imagem_header=jogo.imagem_header,
        imagem_capa=jogo.imagem_capa,
        url_loja=jogo.url_loja,
        descricao=jogo.descricao,
        nota=(
            snap.nota if snap and snap.nota is not None else jogo.nota
        ),
        numero_avaliacoes=(
            snap.numero_avaliacoes
            if snap and snap.numero_avaliacoes is not None
            else jogo.numero_avaliacoes
        ),
        nota_recente=(
            snap.nota_recente
            if snap and snap.nota_recente is not None
            else jogo.nota_recente
        ),
        recursos=jogo.recursos or [],
        tem_conquistas=jogo.tem_conquistas,
        classificacao_etaria=jogo.classificacao_etaria,
        descritores_conteudo=jogo.descritores_conteudo or [],
        janela_coleta=snap.janela_coleta if snap else None,
        preco_no_momento=(
            snap.preco_no_momento if snap and snap.preco_no_momento is not None
            else jogo.preco_atual
        ),
        preco_normal=(
            snap.preco_normal if snap and snap.preco_normal is not None
            else jogo.preco_normal
        ),
        moeda=(snap.moeda if snap and snap.moeda else jogo.moeda),
        desconto_percentual=(
            snap.desconto_percentual if snap and snap.desconto_percentual is not None
            else jogo.desconto_percentual
        ),
        no_game_pass=(
            snap.no_game_pass if snap and snap.no_game_pass is not None
            else jogo.no_game_pass
        ),
    )


@router.get("/jogos", response_model=list[JogoXbox])
def listar_jogos(
    sessao: Session = Depends(get_db),
    busca: str | None = Query(None, description="filtra por nome ou publicadora"),
    genero: str | None = Query(None, description="filtra por um genero exato"),
    ordenar_por: OrdenarPor = "game_pass",
    ordem: Literal["asc", "desc"] = "desc",
    # `le` alto de proposito: a aba pagina no cliente, entao ela busca o
    # catalogo inteiro de uma vez (o Game Pass tem ~800-1000 jogos no BR).
    limite: int = Query(200, ge=1, le=2000),
) -> list[JogoXbox]:
    """Catalogo Xbox, cada jogo com seu snapshot mais recente."""
    snap, _ = _ultimo_snapshot()

    consulta = select(DimJogoXbox, snap).outerjoin(
        snap, snap.product_id == DimJogoXbox.product_id
    )

    if busca:
        padrao = f"%{busca}%"
        consulta = consulta.where(
            or_(
                DimJogoXbox.nome.ilike(padrao),
                DimJogoXbox.publicadora.ilike(padrao),
            )
        )
    if genero:
        consulta = consulta.where(DimJogoXbox.generos.any(genero))

    if ordenar_por == "game_pass":
        # No Game Pass primeiro, depois alfabetico. `ordem` nao mexe aqui - o
        # que a pessoa quer ao ordenar por "Game Pass" e ver os incluidos no
        # topo, sempre.
        consulta = consulta.order_by(
            nulls_last(desc(DimJogoXbox.no_game_pass)), DimJogoXbox.nome.asc()
        )
    elif ordenar_por == "nota":
        # "Melhor avaliados": um 5.0 de uma unica avaliacao nao e melhor que um
        # 4.6 de milhares. Jogos com poucas avaliacoes caem para o fim, e la
        # dentro seguem ordenados por nota.
        bem_avaliado = case(
            (DimJogoXbox.numero_avaliacoes >= _MINIMO_AVALIACOES_RANKING, 1),
            else_=0,
        )
        consulta = consulta.order_by(
            desc(bem_avaliado),
            nulls_last(desc(DimJogoXbox.nota)),
            nulls_last(desc(DimJogoXbox.numero_avaliacoes)),
        )
    else:
        colunas = {
            "nome": DimJogoXbox.nome,
            "preco": DimJogoXbox.preco_atual,
            "lancamento": DimJogoXbox.data_lancamento,
        }
        coluna = colunas[ordenar_por]
        alvo = desc(coluna) if ordem == "desc" else coluna.asc()
        consulta = consulta.order_by(nulls_last(alvo))

    # Desempate pela PK: sem ele, jogos empatados na coluna de ordenacao saem
    # em ordem arbitraria e a fatia da paginacao client-side "pula" quando o
    # front revalida a consulta.
    consulta = consulta.order_by(DimJogoXbox.product_id.asc()).limit(limite)

    return [
        _montar_jogo(jogo, snapshot)
        for jogo, snapshot in sessao.execute(consulta)
    ]


@router.get("/generos", response_model=list[AgregadoGenero])
def agregar_por_genero(sessao: Session = Depends(get_db)) -> list[AgregadoGenero]:
    """Contagem de jogos por genero. Um jogo conta em todos os generos dele."""
    genero = func.unnest(DimJogoXbox.generos).label("genero")
    consulta = (
        select(genero, func.count(func.distinct(DimJogoXbox.product_id)).label("jogos"))
        .group_by(genero)
        .order_by(desc("jogos"))
    )
    return [
        AgregadoGenero(genero=linha.genero, jogos=linha.jogos)
        for linha in sessao.execute(consulta)
    ]


@router.get("/jogos/{product_id}", response_model=DetalheJogoXbox)
def detalhar_jogo(
    product_id: str, sessao: Session = Depends(get_db)
) -> DetalheJogoXbox:
    """Jogo + toda a serie de preco / Game Pass ja coletada dele."""
    jogo = sessao.get(DimJogoXbox, product_id)
    if jogo is None:
        raise HTTPException(
            status_code=404, detail=f"product_id {product_id} nao monitorado"
        )

    snapshots = list(
        sessao.scalars(
            select(FatoSnapshotJogoXbox)
            .where(FatoSnapshotJogoXbox.product_id == product_id)
            .order_by(FatoSnapshotJogoXbox.janela_coleta)
        )
    )

    return DetalheJogoXbox(
        jogo=_montar_jogo(jogo, snapshots[-1] if snapshots else None),
        serie=[
            PontoSerieXbox(
                janela_coleta=s.janela_coleta,
                preco_no_momento=s.preco_no_momento,
                preco_normal=s.preco_normal,
                desconto_percentual=s.desconto_percentual,
                no_game_pass=s.no_game_pass,
                nota=s.nota,
            )
            for s in snapshots
        ],
        midias=jogo.midias or [],
    )


@router.get("/catalogo", response_model=list[CandidatoJogoXbox])
def buscar_catalogo(
    termo: str = Query(..., min_length=2, max_length=100),
    sessao: Session = Depends(get_db),
) -> list[CandidatoJogoXbox]:
    """Busca na Microsoft Store, marcando o que ja esta em `dim_jogo_xbox`.

    O catalogo Xbox so acompanha quem passou pelo Game Pass ou pela semente
    fixa (`xbox_collector.py`) - um jogo a venda mas fora dos dois (ex.:
    "Grand Theft Auto V", que saiu do Game Pass) nunca aparecia na aba. Este
    endpoint e o `/coletar` abaixo fecham o buraco, no mesmo desenho do
    `/api/steam/catalogo` + `/api/steam/coletar`.
    """
    from services.collectors import xbox_loja

    itens = xbox_loja.buscar(termo, limite=15)
    if not itens:
        return []

    ids = [item["product_id"] for item in itens]
    coletados = set(
        sessao.scalars(
            select(DimJogoXbox.product_id).where(DimJogoXbox.product_id.in_(ids))
        )
    )

    return [
        CandidatoJogoXbox(
            product_id=item["product_id"],
            nome=item["titulo"],
            publicadora=item.get("publicadora"),
            preco_texto=item.get("preco_texto"),
            coletado=item["product_id"] in coletados,
            imagem=item.get("imagem"),
        )
        for item in itens
    ]


@router.post("/coletar", response_model=ResumoColetaXbox)
def coletar(entrada: EntradaColetaXbox) -> ResumoColetaXbox:
    """Coleta um jogo da Microsoft Store agora - achado pelo `/catalogo` acima,
    fora do Game Pass e da semente fixa. Sincrono, mesma logica do
    `/api/steam/coletar`: quem clicou esta esperando na tela, e e so uma ficha
    (uma chamada ao `displaycatalog`), nao um lote - questao de segundos.
    """
    from services.collectors.xbox_collector import XboxCollector
    from services.etl.raw_storage import RawStorage

    settings = get_settings()
    storage = RawStorage(settings.raw_data_path, registrar_no_banco=True)
    coletor = XboxCollector(
        raw_storage=storage, settings=settings, product_ids=[entrada.product_id]
    )

    try:
        execucao = coletor.run(carregar=True)
    except Exception as exc:  # noqa: BLE001 - a tela precisa da mensagem
        logger.warning(
            "coleta Xbox sob demanda falhou",
            extra={"product_id": entrada.product_id, "erro": f"{type(exc).__name__}: {exc}"},
        )
        raise HTTPException(
            status_code=502, detail=f"a coleta falhou: {type(exc).__name__}"
        ) from exc
    finally:
        coletor.close()

    if not execucao.sucesso:
        raise HTTPException(
            status_code=502, detail=execucao.erro or "a coleta nao foi concluida"
        )

    with session_scope() as sessao_local:
        nome = sessao_local.scalar(
            select(DimJogoXbox.nome).where(
                DimJogoXbox.product_id == entrada.product_id
            )
        )

    if nome is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"o product_id {entrada.product_id} nao devolveu ficha da Store. "
                "Pode ser regionalmente indisponivel ou o id estar errado."
            ),
        )

    return ResumoColetaXbox(
        product_id=entrada.product_id,
        nome=nome,
        registros_brutos=execucao.registros_coletados,
        segundos=round(execucao.duracao_segundos, 2),
    )
