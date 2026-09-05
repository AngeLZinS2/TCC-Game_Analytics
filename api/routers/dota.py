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
from sqlalchemy.orm import Session, aliased

from api.schemas import (
    ConfrontoResultado,
    FaixaFormato,
    ResumoConfrontos,
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
    AgendaPartida,
    DimEquipe,
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
def listar_jogos(
    sessao: Session = Depends(get_db),
    apenas_com_dados: bool = True,
) -> list[JogoDisponivel]:
    """Jogos cadastrados e quanto ja foi coletado de cada um.

    **O filtro e ligado por padrao, e isso e uma decisao de tela.** Depois que
    as 73 wikis da Liquipedia entraram, `dim_jogo` tem 74 linhas. Devolver todas
    faria a barra do topo renderizar 74 chips, a maioria levando a telas vazias
    - o seletor viraria uma lista de promessas em vez de um seletor.

    `apenas_com_dados=false` devolve o cadastro inteiro, que e o que uma tela de
    administracao ou o assistente precisam saber.
    """
    equipes = (
        select(DimEquipe.id_jogo, func.count().label("equipes"))
        .group_by(DimEquipe.id_jogo)
        .subquery()
    )
    agenda = (
        select(AgendaPartida.id_jogo, func.count().label("agenda"))
        .group_by(AgendaPartida.id_jogo)
        .subquery()
    )

    consulta = (
        select(
            DimJogo.codigo,
            DimJogo.nome,
            func.count(DimPartida.id_partida).label("partidas"),
            func.coalesce(equipes.c.equipes, 0).label("equipes"),
            func.coalesce(agenda.c.agenda, 0).label("agenda"),
        )
        .outerjoin(DimPartida, DimPartida.id_jogo == DimJogo.id_jogo)
        .outerjoin(equipes, equipes.c.id_jogo == DimJogo.id_jogo)
        .outerjoin(agenda, agenda.c.id_jogo == DimJogo.id_jogo)
        .group_by(
            DimJogo.codigo, DimJogo.nome, equipes.c.equipes, agenda.c.agenda
        )
        .order_by(desc("partidas"), desc("agenda"), desc("equipes"), DimJogo.nome)
    )

    linhas = list(sessao.execute(consulta))
    if apenas_com_dados:
        linhas = [l for l in linhas if l.partidas or l.equipes or l.agenda]

    return [
        JogoDisponivel(
            codigo=linha.codigo,
            nome=linha.nome,
            partidas=linha.partidas,
            equipes=linha.equipes,
            agenda=linha.agenda,
        )
        for linha in linhas
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


@router.get("/resumo-confrontos", response_model=ResumoConfrontos)
def resumo_confrontos(
    jogo: str = "dota2", sessao: Session = Depends(get_db)
) -> ResumoConfrontos:
    """Estatistica do calendario - o resumo de quem nao tem partida detalhada.

    `/resumo` le `dim_partida`, que so existe para Dota 2: os outros treze
    esportes recebiam a pagina inteira zerada tendo confronto, equipe, torneio e
    placar no banco. Este endpoint responde no grao que eles TEM.

    Nao devolve duracao nem jogador, e a ausencia e o dado: o ticker publica
    quem jogou, quando e o placar da serie - nada do que aconteceu dentro dela.
    """
    filtro = DimJogo.codigo == jogo
    base = select(AgendaPartida).join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)

    decididos, futuros, primeiro, ultimo, vitorias_a = sessao.execute(
        select(
            func.count().filter(AgendaPartida.vitoria_a.is_not(None)),
            func.count().filter(AgendaPartida.vitoria_a.is_(None)),
            func.min(AgendaPartida.inicio_previsto),
            func.max(AgendaPartida.inicio_previsto),
            func.count().filter(AgendaPartida.vitoria_a.is_(True)),
        )
        .select_from(AgendaPartida)
        .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
        .where(filtro)
    ).one()

    # Equipes que aparecem no calendario, pelos DOIS lados. Um `count(distinct)`
    # sobre uma coluna so esconderia quem nunca foi listado em primeiro, e a
    # uniao das duas em SQL exigiria subconsulta - com algumas centenas de
    # linhas por jogo, juntar em Python e mais simples e igualmente barato.
    nomes = {
        nome
        for linha in sessao.execute(
            select(AgendaPartida.equipe_a_nome, AgendaPartida.equipe_b_nome)
            .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
            .where(filtro)
        )
        for nome in linha
        if nome
    }
    equipes = len(nomes)

    torneios = sessao.scalar(
        select(func.count(func.distinct(AgendaPartida.torneio)))
        .select_from(AgendaPartida)
        .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
        .where(filtro, AgendaPartida.torneio.is_not(None))
    ) or 0

    por_formato = [
        FaixaFormato(rotulo=rotulo, confrontos=quantos)
        for rotulo, quantos in sessao.execute(
            select(AgendaPartida.formato, func.count())
            .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
            .where(filtro, AgendaPartida.formato.is_not(None))
            .group_by(AgendaPartida.formato)
            # Por NOME e nao por contagem: "Bo1, Bo3, Bo5" e uma escala
            # ordenada, e reordenar por frequencia embaralharia o eixo.
            .order_by(AgendaPartida.formato)
        )
    ]

    por_dia = [
        PartidasPorDia(data=dia, partidas=quantos)
        for dia, quantos in sessao.execute(
            select(
                func.date(AgendaPartida.inicio_previsto).label("dia"), func.count()
            )
            .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
            .where(filtro)
            .group_by("dia")
            .order_by("dia")
        )
    ]

    return ResumoConfrontos(
        decididos=decididos,
        futuros=futuros,
        equipes=equipes,
        torneios=torneios,
        vitorias_lado_a=vitorias_a,
        winrate_lado_a=(100.0 * vitorias_a / decididos) if decididos else None,
        primeiro_confronto=primeiro,
        ultimo_confronto=ultimo,
        por_formato=por_formato,
        por_dia=por_dia,
    )


@router.get("/confrontos", response_model=list[ConfrontoResultado])
def listar_confrontos(
    jogo: str = "dota2",
    limite: int = Query(30, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    sessao: Session = Depends(get_db),
) -> list[ConfrontoResultado]:
    """Confrontos JA DECIDIDOS do calendario, do mais recente para o mais antigo.

    **Por que existe.** A tela de Partidas le `dim_partida`, que so tem linha
    para Dota 2 - a OpenDota e a unica fonte que entrega partida com detalhe de
    jogador. Para os outros 13 jogos cadastrados a tela ficava vazia, embora o
    banco tivesse 693 confrontos COM PLACAR em `agenda_partida`, coletados da
    Liquipedia e do OP.GG. O dado estava la; faltava rota.

    O grao e outro e a tela precisa dizer isso: aqui e "quem venceu a serie",
    nao "o que aconteceu dentro dela". Um 3x1 nao vira tres partidas.

    Ordena por horario decrescente porque a pergunta e "o que aconteceu?", e a
    resposta util comeca pelo ultimo resultado, nao pelo primeiro da temporada.
    """
    equipe_a = aliased(DimEquipe)
    equipe_b = aliased(DimEquipe)

    consulta = (
        select(
            AgendaPartida.id_externo,
            AgendaPartida.equipe_a_nome,
            AgendaPartida.equipe_b_nome,
            AgendaPartida.inicio_previsto,
            AgendaPartida.torneio,
            AgendaPartida.formato,
            AgendaPartida.placar_a,
            AgendaPartida.placar_b,
            AgendaPartida.vitoria_a,
            equipe_a.logo_url,
            equipe_b.logo_url,
            equipe_a.tag,
            equipe_b.tag,
        )
        .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
        .outerjoin(equipe_a, equipe_a.id_equipe == AgendaPartida.id_equipe_a)
        .outerjoin(equipe_b, equipe_b.id_equipe == AgendaPartida.id_equipe_b)
        .where(DimJogo.codigo == jogo)
        # `vitoria_a` nulo e confronto sem resultado publicado - e o que a tela
        # de Proximos Confrontos mostra. Aqui e o oposto dela.
        .where(AgendaPartida.vitoria_a.is_not(None))
        .order_by(desc(AgendaPartida.inicio_previsto))
        .limit(limite)
        .offset((pagina - 1) * limite)
    )

    return [
        ConfrontoResultado(
            id_externo=linha[0],
            equipe_a_nome=linha[1],
            equipe_b_nome=linha[2],
            inicio_previsto=linha[3],
            torneio=linha[4],
            formato=linha[5],
            placar_a=linha[6],
            placar_b=linha[7],
            vitoria_a=linha[8],
            equipe_a_logo=linha[9],
            equipe_b_logo=linha[10],
            equipe_a_tag=linha[11],
            equipe_b_tag=linha[12],
        )
        for linha in sessao.execute(consulta)
    ]


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
