"""Endpoints do dominio de partidas (star schema), filtrados por jogo.

O schema e compartilhado entre Dota 2, LoL e Valorant; o discriminador e
`dim_jogo.codigo`. Todas as rotas aqui aceitam `?jogo=`, com dota2 de padrao -
quando a Fase 3 popular o LoL, o mesmo endpoint ja o atende.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Float, and_, case, cast, desc, func, select
from sqlalchemy.orm import Session

from api.schemas import (
    DetalhePartida,
    FaixaDuracao,
    JogadorNaPartida,
    JogoDisponivel,
    Partida,
    PartidasPorDia,
    ResumoJogador,
    ResumoPartidas,
    ResumoPersonagem,
    FiltrosDisponiveis,
)
from db.models import (
    DimJogador,
    DimJogo,
    DimPartida,
    DimPersonagem,
    FatoPartidaJogador,
)
from db.session import get_db

router = APIRouter(prefix="/api/partidas", tags=["partidas"])

# Largura dos bins do histograma de duracao, em minutos.
FAIXA_DURACAO_MINUTOS = 10

OrdenarHeroi = Literal["winrate", "partidas", "kda", "economia"]


def _id_jogo(sessao: Session, codigo: str) -> int:
    id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == codigo))
    if id_jogo is None:
        raise HTTPException(status_code=404, detail=f"jogo '{codigo}' nao cadastrado")
    return id_jogo


def _vitorias():
    """SUM(vitoria) portavel: booleano -> 0/1."""
    return func.sum(case((FatoPartidaJogador.vitoria.is_(True), 1), else_=0))


def _kda(kills, deaths, assists) -> float | None:
    """(K + A) / D, com D minimo 1 para nao dividir por zero em partida sem morte."""
    if kills is None or assists is None:
        return None
    divisor = max(float(deaths or 0.0), 1.0)
    return round((float(kills) + float(assists)) / divisor, 2)


def _media(valor) -> float | None:
    return round(float(valor), 2) if valor is not None else None


@router.get("/jogos", response_model=list[JogoDisponivel])
def listar_jogos(sessao: Session = Depends(get_db)) -> list[JogoDisponivel]:
    """Jogos cadastrados e quantas partidas cada um ja tem coletadas."""
    consulta = (
        select(
            DimJogo.codigo,
            DimJogo.nome,
            func.count(DimPartida.id_partida).label("partidas"),
        )
        .outerjoin(DimPartida, DimPartida.id_jogo == DimJogo.id_jogo)
        .group_by(DimJogo.codigo, DimJogo.nome)
        .order_by(desc("partidas"))
    )
    return [
        JogoDisponivel(codigo=linha.codigo, nome=linha.nome, partidas=linha.partidas)
        for linha in sessao.execute(consulta)
    ]


@router.get("/filtros", response_model=FiltrosDisponiveis)
def filtros_disponiveis(
    sessao: Session = Depends(get_db), jogo: str = "dota2"
) -> FiltrosDisponiveis:
    """Os valores que existem de fato nas colunas filtraveis de dim_partida.

    Os dropdowns da tela de partidas precisam saber quais ligas e modos existem.
    Derivar isso da PAGINA carregada faria a lista de opcoes mudar conforme a
    pessoa pagina - as opcoes tem que descrever o conjunto inteiro, nao o
    recorte em tela.
    """

    def distintos(coluna):
        consulta = (
            select(coluna)
            .join(DimJogo, DimJogo.id_jogo == DimPartida.id_jogo)
            .where(DimJogo.codigo == jogo, coluna.is_not(None))
            .distinct()
            .order_by(coluna)
        )
        return [valor for (valor,) in sessao.execute(consulta)]

    return FiltrosDisponiveis(
        ligas=distintos(DimPartida.liga_nome),
        modos=distintos(DimPartida.modo),
        patches=distintos(DimPartida.patch),
    )


@router.get("/resumo", response_model=ResumoPartidas)
def resumo(sessao: Session = Depends(get_db), jogo: str = "dota2") -> ResumoPartidas:
    """KPIs do dominio + o histograma de duracao das partidas."""
    id_jogo = _id_jogo(sessao, jogo)

    agregados = sessao.execute(
        select(
            func.count(DimPartida.id_partida),
            func.avg(DimPartida.duracao_segundos),
            func.percentile_cont(0.5).within_group(DimPartida.duracao_segundos),
            func.min(DimPartida.data_inicio),
            func.max(DimPartida.data_inicio),
        ).where(DimPartida.id_jogo == id_jogo)
    ).one()

    distintos = sessao.execute(
        select(
            func.count(func.distinct(FatoPartidaJogador.id_jogador)),
            func.count(func.distinct(FatoPartidaJogador.id_personagem)),
        ).where(FatoPartidaJogador.id_jogo == id_jogo)
    ).one()

    # Winrate do lado radiant: uma partida gera 10 linhas de fato, entao a conta
    # e sobre partidas distintas, nunca sobre linhas.
    total_no_fato, vitorias_radiant = sessao.execute(
        select(
            func.count(func.distinct(FatoPartidaJogador.id_partida)),
            func.count(
                func.distinct(
                    case(
                        (
                            and_(
                                FatoPartidaJogador.equipe == "radiant",
                                FatoPartidaJogador.vitoria.is_(True),
                            ),
                            FatoPartidaJogador.id_partida,
                        )
                    )
                )
            ),
        ).where(FatoPartidaJogador.id_jogo == id_jogo)
    ).one()
    winrate_radiant = (
        round(100.0 * vitorias_radiant / total_no_fato, 1) if total_no_fato else None
    )

    faixa = (
        func.floor(DimPartida.duracao_segundos / (FAIXA_DURACAO_MINUTOS * 60))
        * FAIXA_DURACAO_MINUTOS
    ).label("minuto_inicial")
    histograma = sessao.execute(
        select(faixa, func.count().label("partidas"))
        .where(
            DimPartida.id_jogo == id_jogo,
            DimPartida.duracao_segundos.isnot(None),
        )
        .group_by(faixa)
        .order_by(faixa)
    ).all()

    return ResumoPartidas(
        partidas=agregados[0],
        jogadores_distintos=distintos[0],
        personagens_usados=distintos[1],
        duracao_media_segundos=_media(agregados[1]),
        duracao_mediana_segundos=_media(agregados[2]),
        winrate_radiant=winrate_radiant,
        primeira_partida=agregados[3],
        ultima_partida=agregados[4],
        distribuicao_duracao=[
            FaixaDuracao(
                rotulo="{}-{} min".format(
                    int(linha.minuto_inicial),
                    int(linha.minuto_inicial) + FAIXA_DURACAO_MINUTOS,
                ),
                minuto_inicial=int(linha.minuto_inicial),
                partidas=linha.partidas,
            )
            for linha in histograma
        ],
    )


@router.get("/por-dia", response_model=list[PartidasPorDia])
def partidas_por_dia(
    sessao: Session = Depends(get_db), jogo: str = "dota2"
) -> list[PartidasPorDia]:
    """Volume de partidas por dia de disputa."""
    id_jogo = _id_jogo(sessao, jogo)
    dia = func.date(DimPartida.data_inicio).label("dia")

    consulta = (
        select(dia, func.count().label("partidas"))
        .where(DimPartida.id_jogo == id_jogo, DimPartida.data_inicio.isnot(None))
        .group_by(dia)
        .order_by(dia)
    )
    return [
        PartidasPorDia(data=linha.dia, partidas=linha.partidas)
        for linha in sessao.execute(consulta)
    ]


@router.get("/personagens", response_model=list[ResumoPersonagem])
def listar_personagens(
    sessao: Session = Depends(get_db),
    jogo: str = "dota2",
    min_partidas: int = Query(5, ge=1, description="corta a cauda de amostra pequena"),
    ordenar_por: OrdenarHeroi = "winrate",
    limite: int = Query(50, ge=1, le=200),
) -> list[ResumoPersonagem]:
    """Winrate e medias por personagem.

    `min_partidas` existe porque um heroi com 2 jogos e 2 vitorias tem 100% de
    winrate e nenhum significado - sem o corte ele lidera qualquer ranking.
    """
    id_jogo = _id_jogo(sessao, jogo)

    partidas = func.count().label("partidas")
    vitorias = _vitorias().label("vitorias")
    winrate = (100.0 * cast(vitorias, Float) / partidas).label("winrate")
    kills = func.avg(FatoPartidaJogador.kills).label("kills")
    deaths = func.avg(FatoPartidaJogador.deaths).label("deaths")
    assists = func.avg(FatoPartidaJogador.assists).label("assists")
    gpm = func.avg(FatoPartidaJogador.economia_por_minuto).label("gpm")
    xpm = func.avg(FatoPartidaJogador.experiencia_por_minuto).label("xpm")

    ordenacoes = {
        "winrate": desc(winrate),
        "partidas": desc(partidas),
        "kda": desc((kills + assists) / func.greatest(deaths, 1.0)),
        "economia": desc(gpm),
    }

    consulta = (
        select(
            DimPersonagem.id_personagem,
            DimPersonagem.nome,
            DimPersonagem.nome_interno,
            partidas,
            vitorias,
            winrate,
            kills,
            deaths,
            assists,
            gpm,
            xpm,
        )
        .join(
            DimPersonagem,
            DimPersonagem.id_personagem == FatoPartidaJogador.id_personagem,
        )
        .where(FatoPartidaJogador.id_jogo == id_jogo)
        .group_by(
            DimPersonagem.id_personagem,
            DimPersonagem.nome,
            DimPersonagem.nome_interno,
        )
        .having(func.count() >= min_partidas)
        .order_by(ordenacoes[ordenar_por], desc(partidas))
        .limit(limite)
    )

    return [
        ResumoPersonagem(
            id_personagem=linha.id_personagem,
            nome=linha.nome,
            nome_interno=linha.nome_interno,
            partidas=linha.partidas,
            vitorias=linha.vitorias,
            winrate=round(float(linha.winrate), 1),
            kda_medio=_kda(linha.kills, linha.deaths, linha.assists),
            kills_media=_media(linha.kills),
            deaths_media=_media(linha.deaths),
            assists_media=_media(linha.assists),
            economia_por_minuto_media=_media(linha.gpm),
            experiencia_por_minuto_media=_media(linha.xpm),
        )
        for linha in sessao.execute(consulta)
    ]


@router.get("/jogadores", response_model=list[ResumoJogador])
def listar_jogadores(
    sessao: Session = Depends(get_db),
    jogo: str = "dota2",
    min_partidas: int = Query(3, ge=1),
    limite: int = Query(50, ge=1, le=200),
) -> list[ResumoJogador]:
    """Jogadores identificados, ordenados por volume de partidas."""
    id_jogo = _id_jogo(sessao, jogo)

    # Heroi assinatura: o mais escolhido pelo jogador, com quantas vezes.
    # Sai de uma janela em vez de um segundo GROUP BY porque o que se quer e
    # "a primeira linha de cada jogador quando ordenado por contagem" - que e
    # exatamente o que `row_number` responde, numa varredura so.
    contagem_heroi = (
        select(
            FatoPartidaJogador.id_jogador.label("id_jogador"),
            DimPersonagem.nome.label("personagem"),
            func.count().label("vezes"),
            func.row_number()
            .over(
                partition_by=FatoPartidaJogador.id_jogador,
                order_by=(desc(func.count()), DimPersonagem.nome),
            )
            .label("posicao"),
        )
        .join(
            DimPersonagem,
            DimPersonagem.id_personagem == FatoPartidaJogador.id_personagem,
        )
        .where(
            FatoPartidaJogador.id_jogo == id_jogo,
            FatoPartidaJogador.id_jogador.is_not(None),
        )
        .group_by(FatoPartidaJogador.id_jogador, DimPersonagem.nome)
        .subquery()
    )

    assinatura = (
        select(
            contagem_heroi.c.id_jogador,
            contagem_heroi.c.personagem,
            contagem_heroi.c.vezes,
        )
        .where(contagem_heroi.c.posicao == 1)
        .subquery()
    )

    partidas = func.count().label("partidas")
    vitorias = _vitorias().label("vitorias")

    consulta = (
        select(
            DimJogador.id_jogador,
            DimJogador.nome,
            partidas,
            vitorias,
            (100.0 * cast(vitorias, Float) / partidas).label("winrate"),
            func.avg(FatoPartidaJogador.kills).label("kills"),
            func.avg(FatoPartidaJogador.deaths).label("deaths"),
            func.avg(FatoPartidaJogador.assists).label("assists"),
            func.avg(FatoPartidaJogador.economia_por_minuto).label("gpm"),
            assinatura.c.personagem.label("assinatura"),
            assinatura.c.vezes.label("assinatura_vezes"),
        )
        .join(DimJogador, DimJogador.id_jogador == FatoPartidaJogador.id_jogador)
        .outerjoin(assinatura, assinatura.c.id_jogador == DimJogador.id_jogador)
        .where(FatoPartidaJogador.id_jogo == id_jogo)
        .group_by(
            DimJogador.id_jogador,
            DimJogador.nome,
            assinatura.c.personagem,
            assinatura.c.vezes,
        )
        .having(func.count() >= min_partidas)
        .order_by(desc(partidas), desc("winrate"))
        .limit(limite)
    )

    return [
        ResumoJogador(
            id_jogador=linha.id_jogador,
            nome=linha.nome,
            partidas=linha.partidas,
            vitorias=linha.vitorias,
            winrate=round(float(linha.winrate), 1),
            kda_medio=_kda(linha.kills, linha.deaths, linha.assists),
            economia_por_minuto_media=_media(linha.gpm),
            personagem_assinatura=linha.assinatura,
            partidas_assinatura=linha.assinatura_vezes,
        )
        for linha in sessao.execute(consulta)
    ]


@router.get("", response_model=list[Partida])
def listar_partidas(
    sessao: Session = Depends(get_db),
    jogo: str = "dota2",
    liga: str | None = Query(None, description="filtra pelo nome da liga"),
    desde: date | None = Query(None, description="data minima de inicio"),
    limite: int = Query(50, ge=1, le=200),
    deslocamento: int = Query(0, ge=0),
) -> list[Partida]:
    """Partidas mais recentes primeiro, com o lado vencedor ja resolvido."""
    id_jogo = _id_jogo(sessao, jogo)

    # O vencedor vive no fato (uma linha por jogador). O MAX sobre o CASE resolve
    # o lado vitorioso no mesmo SELECT, em vez de uma consulta por partida.
    vencedor = func.max(
        case((FatoPartidaJogador.vitoria.is_(True), FatoPartidaJogador.equipe))
    ).label("vencedor")

    consulta = (
        select(DimPartida, vencedor)
        .outerjoin(
            FatoPartidaJogador,
            FatoPartidaJogador.id_partida == DimPartida.id_partida,
        )
        .where(DimPartida.id_jogo == id_jogo)
    )
    if liga:
        consulta = consulta.where(DimPartida.liga_nome.ilike(f"%{liga}%"))
    if desde:
        consulta = consulta.where(DimPartida.data_inicio >= desde)

    consulta = (
        consulta.group_by(DimPartida.id_partida)
        .order_by(desc(DimPartida.data_inicio))
        .limit(limite)
        .offset(deslocamento)
    )

    return [
        _montar_partida(partida, lado)
        for partida, lado in sessao.execute(consulta)
    ]


def _montar_partida(partida: DimPartida, vencedor: str | None) -> Partida:
    return Partida(
        id_partida=partida.id_partida,
        id_externo=partida.id_externo,
        data_inicio=partida.data_inicio,
        duracao_segundos=partida.duracao_segundos,
        modo=partida.modo,
        tipo_partida=partida.tipo_partida,
        patch=partida.patch,
        liga_nome=partida.liga_nome,
        vencedor=vencedor,
    )


@router.get("/{id_partida}", response_model=DetalhePartida)
def detalhar_partida(
    id_partida: int, sessao: Session = Depends(get_db)
) -> DetalhePartida:
    """Placar completo: a partida e as linhas de fato dela."""
    partida = sessao.get(DimPartida, id_partida)
    if partida is None:
        raise HTTPException(status_code=404, detail=f"partida {id_partida} nao existe")

    linhas = sessao.execute(
        select(
            FatoPartidaJogador,
            DimPersonagem.nome,
            # O nome interno vem junto porque a tela monta o retrato do heroi
            # a partir dele - `npc_dota_hero_luna` vira `luna.png` na CDN da
            # Valve, entao a imagem nao precisa ser coletada nem armazenada.
            DimPersonagem.nome_interno,
            DimJogador.nome,
        )
        .outerjoin(
            DimPersonagem,
            DimPersonagem.id_personagem == FatoPartidaJogador.id_personagem,
        )
        .outerjoin(DimJogador, DimJogador.id_jogador == FatoPartidaJogador.id_jogador)
        .where(FatoPartidaJogador.id_partida == id_partida)
        .order_by(FatoPartidaJogador.slot)
    ).all()

    vencedor = next(
        (fato.equipe for fato, _, _, _ in linhas if fato.vitoria is True), None
    )

    return DetalhePartida(
        partida=_montar_partida(partida, vencedor),
        jogadores=[
            JogadorNaPartida(
                slot=fato.slot,
                equipe=fato.equipe,
                vitoria=fato.vitoria,
                jogador=nome_jogador,
                id_jogador=fato.id_jogador,
                personagem=nome_personagem,
                personagem_interno=interno_personagem,
                kills=fato.kills,
                deaths=fato.deaths,
                assists=fato.assists,
                economia=fato.economia,
                economia_por_minuto=fato.economia_por_minuto,
                experiencia_por_minuto=fato.experiencia_por_minuto,
                last_hits=fato.last_hits,
                denies=fato.denies,
                nivel=fato.nivel,
                dano_causado=fato.dano_causado,
                pontos_objetivo=fato.pontos_objetivo,
                metricas_extras=fato.metricas_extras,
            )
            for fato, nome_personagem, interno_personagem, nome_jogador in linhas
        ],
    )
