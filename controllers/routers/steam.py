"""Endpoints do dominio catalogo/mercado (Steam).

A tabela de fato tem uma linha por (app_id, janela_coleta). Quase toda tela do
dashboard quer "o estado agora", que e o snapshot mais recente de cada jogo -
por isso o DISTINCT ON aparece em varios lugares aqui.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, desc, func, nulls_last, or_, select
from sqlalchemy.orm import Session, aliased

from decimal import Decimal

from views.schemas import (
    AgregadoCategoria,
    AgregadoGenero,
    DetalheJogoSteam,
    DlcEmPromocao,
    FichaJogoSteam,
    JogoSteam,
    MaisJogadoSteam,
    MenorPrecoHistorico,
    NoticiaSteam,
    OfertaLoja,
    PontoHistoricoPrecoSteam,
    PontoSerie,
    PontoSerieTotal,
    PromocaoAtivaSteam,
    SerieJogadoresJogo,
)
from models.models import (
    DimAppSteamNome,
    DimJogoSteam,
    FatoSnapshotJogoSteam,
    HistoricoPrecoSteam,
    NoticiaJogoSteam,
    OfertaJogoSteam,
    PromocaoSteam,
)
from models.session import get_db
from config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/steam", tags=["steam"])

OrdenarPor = Literal[
    "jogadores", "avaliacoes", "numero_avaliacoes", "preco", "metacritic", "nome"
]


# ---------------------------------------------------------------------------
# Top 100 mais jogados da Steam AGORA - ao vivo, com cache curto
# ---------------------------------------------------------------------------
#
# O ranking nao mora no banco: a Valve publica o estado deste instante e a home
# quer exatamente isso. O que o banco guarda e so o NOME de cada app_id
# (`dim_app_steam_nome`, preenchido pelo coletor `steam_online`).
_URL_CONCORRENTES = (
    "https://api.steampowered.com/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"
)
_URL_MAIS_JOGADOS = (
    "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"
)
#: Cache de processo. A Valve atualiza o numero a cada poucos minutos; segurar
#: por 90s corta a rajada de requests sem a lista ficar velha de verdade.
_CACHE_TTL_S = 90
_cache: dict[str, object] = {"em": 0.0, "ranks": []}


def _buscar_ranks_valve() -> list[dict]:
    """Junta `concurrent_in_game` (ranking atual) com `last_week_rank` (movimento)."""
    agora = time.monotonic()
    if agora - float(_cache["em"]) < _CACHE_TTL_S and _cache["ranks"]:
        return _cache["ranks"]  # type: ignore[return-value]

    def _get(url: str) -> list[dict]:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return ((resp.json() or {}).get("response") or {}).get("ranks") or []
        except (requests.RequestException, ValueError) as exc:
            logger.warning("charts da Steam falharam: %s", exc)
            return []

    concorrentes = _get(_URL_CONCORRENTES)
    semana = {r["appid"]: r.get("last_week_rank") for r in _get(_URL_MAIS_JOGADOS)}

    ranks = [
        {
            "posicao": r["rank"],
            "app_id": r["appid"],
            "jogadores_agora": r.get("concurrent_in_game") or 0,
            "pico_24h": r.get("peak_in_game"),
            "rank_semana": semana.get(r["appid"]),
        }
        for r in concorrentes
        if isinstance(r.get("appid"), int)
    ]

    if ranks:  # so cacheia sucesso - senao um blip da Valve congela a lista
        _cache["em"] = agora
        _cache["ranks"] = ranks
    return ranks or _cache["ranks"]  # type: ignore[return-value]


@router.get("/mais-jogados", response_model=list[MaisJogadoSteam])
def mais_jogados(
    limite: int = Query(100, ge=1, le=100),
    sessao: Session = Depends(get_db),
) -> list[MaisJogadoSteam]:
    """O Top N mais jogados da Steam neste instante, direto da Valve.

    Sempre fresco (cache de 90s). Nome de cada jogo vem do banco -
    `dim_jogo_steam` para os monitorados, `dim_app_steam_nome` (cache do
    coletor) para o resto; `null` enquanto o coletor nao resolveu.
    """
    ranks = _buscar_ranks_valve()[:limite]
    if not ranks:
        raise HTTPException(status_code=503, detail="ranking da Steam indisponível")

    ids = [r["app_id"] for r in ranks]
    nomes = dict(
        sessao.execute(
            select(DimJogoSteam.app_id, DimJogoSteam.nome).where(
                DimJogoSteam.app_id.in_(ids)
            )
        ).all()
    )
    for app_id, nome in sessao.execute(
        select(DimAppSteamNome.app_id, DimAppSteamNome.nome).where(
            DimAppSteamNome.app_id.in_(ids)
        )
    ).all():
        nomes.setdefault(app_id, nome)

    def _mov(pos: int, rank_semana: int | None) -> int | None:
        if rank_semana is None:
            return None
        return rank_semana - pos  # >0 subiu (estava mais embaixo), <0 caiu

    return [
        MaisJogadoSteam(
            posicao=r["posicao"],
            app_id=r["app_id"],
            nome=nomes.get(r["app_id"]),
            jogadores_agora=r["jogadores_agora"],
            pico_24h=r["pico_24h"],
            variacao_semana=_mov(r["posicao"], r["rank_semana"]),
        )
        for r in ranks
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


#: Orgaos de classificacao que a tela mostra. `steam_germany`, `igrs`,
#: `gmedia` e afins existem no payload mas so poluem - a Steam ja mostra so
#: os principais na loja.
_ORGAOS_RELEVANTES = ("esrb", "pegi", "usk", "dejus", "cero", "oflc", "kgrb")

#: Feeds cujo post e do proprio estudio - "atualizacao" de verdade. O resto e
#: cobertura de imprensa que a Steam agrega no mesmo endpoint.
_FEEDS_OFICIAIS = (
    "Community Announcements",
    "Steam Community Announcements",
    "Product Update",
)


def _montar_ficha(jogo: DimJogoSteam) -> FichaJogoSteam:
    tags = jogo.tags_comunidade or {}
    classificacoes = {
        org: nota
        for org, nota in (jogo.classificacoes or {}).items()
        if org in _ORGAOS_RELEVANTES and str(nota).lower() not in ("", "banned")
    }
    return FichaJogoSteam(
        tipo=jogo.tipo,
        recursos=jogo.recursos or [],
        plataformas=jogo.plataformas or [],
        idiomas=jogo.idiomas or [],
        idiomas_com_audio=jogo.idiomas_com_audio or [],
        faixa_etaria=jogo.faixa_etaria,
        descritores_conteudo=jogo.descritores_conteudo or [],
        classificacoes=classificacoes,
        suporte_controle=jogo.suporte_controle,
        conquistas_total=jogo.conquistas_total,
        conquistas_destaque=jogo.conquistas_destaque or [],
        analises_totais=jogo.analises_totais,
        dlc_ids=jogo.dlc_ids or [],
        site_oficial=jogo.site_oficial,
        imagem_header=jogo.imagem_header,
        em_breve=jogo.em_breve,
        requisitos_minimos=jogo.requisitos_minimos,
        requisitos_recomendados=jogo.requisitos_recomendados,
        midias=jogo.midias or [],
        donos_estimados=jogo.donos_estimados,
        tempo_jogo_medio_min=jogo.tempo_jogo_medio_min,
        tempo_jogo_mediano_min=jogo.tempo_jogo_mediano_min,
        tags_comunidade=sorted(tags.items(), key=lambda kv: kv[1], reverse=True)[:20],
        coletado_ficha_em=jogo.coletado_ficha_em,
        hltb_id=jogo.hltb_id or None,
        hltb_nome=jogo.hltb_nome,
        hltb_horas_historia=jogo.hltb_horas_historia,
        hltb_horas_extras=jogo.hltb_horas_extras,
        hltb_horas_completista=jogo.hltb_horas_completista,
        coletado_tempo_em=jogo.coletado_tempo_em,
    )


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
        imagem_header=jogo.imagem_header,
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
    categoria: str | None = Query(
        None,
        description=(
            "filtra por uma categoria exata da Steam (recursos: Single-player, "
            "Multi-player, Co-op, Conquistas da Steam...) - diferente de genero"
        ),
    ),
    ordenar_por: OrdenarPor = "jogadores",
    ordem: Literal["asc", "desc"] = "desc",
    limite: int = Query(100, ge=1, le=500),
) -> list[JogoSteam]:
    """Catalogo monitorado, cada jogo com seu snapshot mais recente.

    "Monitorado" quer dizer COM FICHA coletada (`appdetails`), nao "tem linha
    em `dim_jogo_steam`". A varredura de ofertas (Fase 35.1) povoa a dimensao
    com ~18 mil apps que so tem nome, imagem e tags - sem genero, preco,
    avaliacao nem telemetria. Devolve-los aqui enchia a tabela de telemetria
    de linhas vazias e, pior, fazia a busca do catalogo "achar" o jogo e
    portanto nunca oferecer a coleta dele.
    """
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
        .where(DimJogoSteam.com_ficha())
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
    if categoria:
        consulta = consulta.where(DimJogoSteam.recursos.any(categoria))

    coluna = ordenacoes[ordenar_por]
    alvo = desc(coluna) if ordem == "desc" else coluna.asc()
    # nulls_last nas duas direcoes: jogo sem snapshot nunca lidera o ranking.
    # `app_id` como desempate: sem ele a fatia da paginacao client-side "pula"
    # entre jogos empatados quando o front revalida.
    consulta = consulta.order_by(nulls_last(alvo), DimJogoSteam.app_id.asc()).limit(limite)

    return [
        _montar_jogo(jogo, snapshot, pico, anterior)
        for jogo, snapshot, pico, anterior in sessao.execute(consulta)
    ]


@router.get("/generos", response_model=list[AgregadoGenero])
def agregar_por_genero(sessao: Session = Depends(get_db)) -> list[AgregadoGenero]:
    """Um jogo conta em todos os seus generos - a soma passa do total de jogos.

    Conta o MESMO universo que `listar_jogos` devolve (so quem tem ficha): este
    numero e o contador do filtro, e um filtro que promete 151 jogos e entrega
    137 esta mentindo. A diferenca vem das linhas que a varredura de ofertas
    criou sem ficha.
    """
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
        .where(DimJogoSteam.com_ficha())
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


@router.get("/categorias", response_model=list[AgregadoCategoria])
def agregar_por_categoria(sessao: Session = Depends(get_db)) -> list[AgregadoCategoria]:
    """As categorias da Steam (`recursos`: Single-player, Co-op, Conquistas...)
    presentes no catalogo, com quantos jogos tem cada uma - o dropdown de
    filtro pede essa lista pronta, em vez de descobrir os valores existentes
    varrendo a tabela toda no navegador.

    Diferente de genero (um punhado de generos grossos, cabe em chip): a
    Steam tem 50+ categorias, e o volume e o motivo do filtro ser um
    `<select>` e nao uma fileira de chips.
    """
    # `unnest()` nao pode ir direto no WHERE/HAVING (o Postgres recusa
    # set-returning function nos dois) - por isso o unnest mora numa
    # subconsulta, e o filtro entra na consulta de fora, sobre a coluna ja
    # expandida.
    #
    # O `where` da ficha esta aqui pelo mesmo motivo de `/generos`: o contador
    # do filtro tem que falar do mesmo universo que a listagem devolve.
    expandido = (
        select(
            DimJogoSteam.app_id, func.unnest(DimJogoSteam.recursos).label("categoria")
        )
        .where(DimJogoSteam.com_ficha())
        .subquery()
    )

    consulta = (
        select(
            expandido.c.categoria,
            func.count(func.distinct(expandido.c.app_id)).label("jogos"),
        )
        # A Steam as vezes deixa uma chave de traducao sem resolver
        # ("#category_playable_at_your_own_pace") escapar do payload - lixo de
        # exibicao, nao categoria de verdade.
        .where(~expandido.c.categoria.like("#%"))
        .group_by(expandido.c.categoria)
        .order_by(desc("jogos"))
    )

    return [
        AgregadoCategoria(categoria=linha.categoria, jogos=linha.jogos)
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

    noticias = list(
        sessao.scalars(
            select(NoticiaJogoSteam)
            .where(NoticiaJogoSteam.app_id == app_id)
            # Post oficial do estudio primeiro (e o que "atualizacao" quer
            # dizer), depois a cobertura externa - e, dentro de cada grupo,
            # do mais recente.
            .order_by(
                case(
                    (
                        or_(
                            NoticiaJogoSteam.feed.is_(None),
                            NoticiaJogoSteam.feed.in_(_FEEDS_OFICIAIS),
                        ),
                        0,
                    ),
                    else_=1,
                ),
                nulls_last(desc(NoticiaJogoSteam.publicado_em)),
            )
            .limit(8)
        )
    )

    ofertas_raw = list(
        sessao.scalars(
            select(OfertaJogoSteam)
            .where(OfertaJogoSteam.app_id == app_id)
            .order_by(OfertaJogoSteam.preco)
        )
    )
    ofertas = [
        OfertaLoja(
            loja=o.loja,
            preco=o.preco,
            preco_normal=o.preco_normal,
            desconto=o.desconto,
            moeda=o.moeda,
            url=o.url,
            drm=o.drm,
            melhor=(i == 0),
        )
        for i, o in enumerate(ofertas_raw)
    ]
    menor_historico = (
        MenorPrecoHistorico(
            preco=jogo.menor_preco_historico,
            loja=jogo.menor_preco_historico_loja,
            moeda=jogo.menor_preco_historico_moeda,
            data=jogo.menor_preco_historico_em,
        )
        if jogo.menor_preco_historico is not None
        else None
    )

    # --- Preco primeiro-partido da Steam (Fase 35) - distinto do `ofertas`/
    # `menor_historico` acima, que sao cross-loja via ITAD e nao mudam aqui.
    promocao = sessao.scalar(
        select(PromocaoSteam).where(
            PromocaoSteam.app_id == app_id, PromocaoSteam.ativa.is_(True)
        )
    )
    promocao_ativa = (
        PromocaoAtivaSteam(
            preco_original=Decimal(promocao.preco_original) / 100,
            preco_final=Decimal(promocao.preco_final) / 100,
            desconto_percentual=promocao.desconto_percentual,
            moeda=promocao.moeda,
            iniciada_em=promocao.iniciada_em,
        )
        if promocao is not None
        else None
    )
    historico_preco_steam = [
        PontoHistoricoPrecoSteam(
            registrado_em=linha.registrado_em,
            preco_final=Decimal(linha.preco_final) / 100,
            desconto_percentual=linha.desconto_percentual,
        )
        for linha in sessao.scalars(
            select(HistoricoPrecoSteam)
            .where(HistoricoPrecoSteam.app_id == app_id)
            .order_by(HistoricoPrecoSteam.registrado_em)
        )
    ]

    # As DLCs deste jogo que estao em promocao agora. A lista de Ofertas so
    # mostra jogo (ver `steam_ofertas.py`), entao este e o unico lugar onde a
    # promocao de uma DLC aparece - ao lado do jogo dono dela, que e o
    # contexto em que ela significa alguma coisa.
    #
    # `dlc_ids` vem do `appdetails`, entao existe so pra jogo com ficha; sem
    # ela a lista fica vazia, sem consulta nenhuma.
    dlc_em_promocao: list[DlcEmPromocao] = []
    if jogo.dlc_ids:
        dlc_em_promocao = [
            DlcEmPromocao(
                app_id=promocao.app_id,
                nome=dlc.nome,
                imagem_header=dlc.imagem_header,
                preco_original=Decimal(promocao.preco_original) / 100,
                preco_final=Decimal(promocao.preco_final) / 100,
                desconto_percentual=promocao.desconto_percentual,
                moeda=promocao.moeda,
            )
            for promocao, dlc in sessao.execute(
                select(PromocaoSteam, DimJogoSteam)
                .join(DimJogoSteam, DimJogoSteam.app_id == PromocaoSteam.app_id)
                .where(
                    PromocaoSteam.app_id.in_(jogo.dlc_ids),
                    PromocaoSteam.ativa.is_(True),
                )
                .order_by(desc(PromocaoSteam.desconto_percentual))
            )
        ]

    return DetalheJogoSteam(
        ficha_coletada=jogo.coletado_ficha_em is not None,
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
        ficha=_montar_ficha(jogo),
        noticias=[
            NoticiaSteam(
                gid=n.gid,
                titulo=n.titulo,
                url=n.url,
                autor=n.autor,
                feed=n.feed,
                publicado_em=n.publicado_em,
                resumo=n.resumo,
            )
            for n in noticias
        ],
        ofertas=ofertas,
        menor_preco_historico=menor_historico,
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
        promocao_ativa=promocao_ativa,
        historico_preco_steam=historico_preco_steam,
        dlc_em_promocao=dlc_em_promocao,
    )


@router.get("/serie-total", response_model=list[PontoSerieTotal])
def serie_total(
    sessao: Session = Depends(get_db),
    dias: int | None = Query(None, ge=1, le=3650),
) -> list[PontoSerieTotal]:
    """Jogadores simultaneos somados sobre todo o catalogo, por janela de coleta.

    E a serie que o sparkline do KPI desenha. Somar no banco e nao no navegador
    importa porque a alternativa seria baixar a serie inteira de cada jogo so
    para reduzi-la a um numero por janela.

    `dias` recorta a janela de tempo (o seletor de periodo da tela). Sem ele, a
    serie inteira - que e tambem como a tela descobre QUANTO historico existe,
    para nao oferecer um periodo maior do que o que foi coletado.
    """
    consulta = select(
        FatoSnapshotJogoSteam.janela_coleta.label("janela_coleta"),
        func.sum(FatoSnapshotJogoSteam.jogadores_simultaneos).label("jogadores"),
        func.count(func.distinct(FatoSnapshotJogoSteam.app_id)).label("jogos"),
    )
    if dias is not None:
        corte = datetime.now(timezone.utc) - timedelta(days=dias)
        consulta = consulta.where(FatoSnapshotJogoSteam.janela_coleta >= corte)
    consulta = consulta.group_by(FatoSnapshotJogoSteam.janela_coleta).order_by(
        FatoSnapshotJogoSteam.janela_coleta
    )
    return _sem_janela_incompleta(
        [
            PontoSerieTotal(
                janela_coleta=janela, jogadores_simultaneos=jogadores, jogos=jogos
            )
            for janela, jogadores, jogos in sessao.execute(consulta)
        ]
    )


#: Pontos por jogo no mini-grafico do ranking. Um fio de ~40px nao comporta as
#: 97 janelas que ja existem, e mandar todas so engordaria a resposta.
_PONTOS_SERIE_RANKING = 24


#: Cobertura minima, sobre a melhor janela do recorte, para uma janela entrar
#: na serie agregada. Uma janela com 10 dos ~160 jogos nao mede o catalogo -
#: mede dez jogos.
_COBERTURA_MINIMA = 0.5


def _sem_janela_incompleta(
    pontos: list[PontoSerieTotal],
) -> list[PontoSerieTotal]:
    """Corta as janelas do FIM que a coleta nao chegou a preencher.

    A coleta percorre o catalogo ao longo da janela, e quando ela e
    interrompida no meio a janela fica com uma fracao dos jogos. Somar essa
    fracao e comparar com a janela anterior compara populacoes diferentes:
    medido aqui, 154 jogos numa janela e 10 na seguinte viravam "-100%" e um
    sparkline despencando ate o chao - sem que jogador nenhum tivesse saido.

    So o FIM e cortado: um buraco no meio da serie e historico de verdade
    (a coleta ficou fora do ar naquele dia) e continua a vista.
    """
    if not pontos:
        return pontos
    melhor = max(p.jogos for p in pontos)
    if melhor <= 0:
        return pontos
    # O proprio ponto de melhor cobertura para o laco, entao `corte` nunca
    # chega a zero: uma serie toda rala (catalogo novo, poucos jogos em todas
    # as janelas) volta inteira, que e o certo.
    corte = len(pontos)
    while pontos[corte - 1].jogos < melhor * _COBERTURA_MINIMA:
        corte -= 1
    return pontos[:corte]


@router.get("/series-jogadores", response_model=list[SerieJogadoresJogo])
def series_jogadores(
    sessao: Session = Depends(get_db),
    app_ids: str = Query(..., description="app_ids separados por virgula"),
    dias: int | None = Query(None, ge=1, le=3650),
) -> list[SerieJogadoresJogo]:
    """Serie recente de jogadores simultaneos de varios jogos, numa chamada.

    Existe para o mini-grafico de cada linha do ranking: sem ele, a tela teria
    de pedir a ficha completa de cada jogo (uma requisicao por linha) so para
    extrair a serie. Devolve so os ultimos `_PONTOS_SERIE_RANKING` pontos de
    cada jogo.
    """
    ids: list[int] = []
    for pedaco in app_ids.split(","):
        pedaco = pedaco.strip()
        if pedaco.isdigit():
            ids.append(int(pedaco))
    # Teto defensivo: o ranking mostra dez linhas; um `app_ids` gigante viraria
    # uma varredura da tabela de fato inteira.
    ids = ids[:50]
    if not ids:
        return []

    consulta = select(
        FatoSnapshotJogoSteam.app_id,
        FatoSnapshotJogoSteam.janela_coleta,
        FatoSnapshotJogoSteam.jogadores_simultaneos,
    ).where(
        FatoSnapshotJogoSteam.app_id.in_(ids),
        FatoSnapshotJogoSteam.jogadores_simultaneos.is_not(None),
    )
    if dias is not None:
        corte = datetime.now(timezone.utc) - timedelta(days=dias)
        consulta = consulta.where(FatoSnapshotJogoSteam.janela_coleta >= corte)
    consulta = consulta.order_by(
        FatoSnapshotJogoSteam.app_id, FatoSnapshotJogoSteam.janela_coleta
    )

    por_jogo: dict[int, list[int]] = {}
    for app_id, _janela, jogadores in sessao.execute(consulta):
        por_jogo.setdefault(app_id, []).append(int(jogadores))

    return [
        SerieJogadoresJogo(app_id=app_id, valores=valores[-_PONTOS_SERIE_RANKING:])
        for app_id, valores in por_jogo.items()
    ]
