"""O ranking OFICIAL de cada esporte, do jeito que a fonte publica.

Diferente de `/api/ml/confronto/ranking`, que e a forca estimada pelo nosso
Bradley-Terry sobre os confrontos coletados: aqui e o ranking que ja existe la
fora - o rating por regiao do vlr.gg em Valorant, o Regional Standings da Valve
em Counter-Strike. O mesmo dado que o modelo usa como PRIOR (Fase 15), mas
exposto direto, porque para o publico de Valorant o ranking do vlr.gg *e* a
referencia, nao um detalhe interno.

Le `ranking_externo` - o snapshot mais recente por jogo - e agrupa por regiao.
Cada esporte tem a sua fonte e as suas regioes; nada aqui e de CS reaproveitado
em Valorant.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.schemas import EquipeRankingOficial, RankingOficialResposta, RegiaoRanking
from db.models import AgendaPartida, DimEquipe, DimJogo, RankingExterno
from db.session import get_db
from etl.agenda_fontes import restringir_recorte

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/esports", tags=["esports"])

#: Como cada fonte se chama e onde o publico confere o original.
FONTES = {
    "vlr": ("vlr.gg", "https://www.vlr.gg/rankings"),
    "valve": ("Valve Regional Standings", "https://github.com/ValveSoftware/counter-strike_regional_standings"),
}

#: Nome de exibicao e ORDEM das regioes. Uma regiao fora deste mapa ainda
#: aparece (com o slug como nome), so vai para o fim da lista.
REGIOES = {
    "north-america": "América do Norte",
    "europe": "Europa",
    "brazil": "Brasil",
    "korea": "Coreia",
    "china": "China",
    "asia-pacific": "Ásia-Pacífico",
    "la-s": "LATAM Sul",
    "la-n": "LATAM Norte",
    "global": "Global",
}


def _ordem_regiao(slug: str | None) -> tuple[int, str]:
    chave = slug or ""
    if chave in REGIOES:
        return (list(REGIOES).index(chave), chave)
    return (len(REGIOES), chave)


@router.get("/ranking-oficial", response_model=RankingOficialResposta)
def ranking_oficial(
    jogo: str = "valorant",
    limite: int = Query(
        30,
        ge=1,
        le=500,
        description=(
            "quantos times por regiao. O vlr.gg lista a ladder inteira (300+ "
            "por regiao); a cauda tem rating ~1000 e nenhuma relevancia."
        ),
    ),
    db: Session = Depends(get_db),
) -> RankingOficialResposta:
    """O ranking publicado da fonte oficial do jogo, por regiao.

    404 quando o jogo nao existe ou nunca teve um snapshot coletado - a tela
    esconde a secao nesse caso, em vez de mostrar uma tabela vazia.
    """
    id_jogo = db.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == jogo))
    if id_jogo is None:
        raise HTTPException(status_code=404, detail=f"jogo {jogo!r} não encontrado")

    ultima: date | None = db.scalar(
        select(func.max(RankingExterno.data_referencia)).where(
            RankingExterno.id_jogo == id_jogo
        )
    )
    if ultima is None:
        # Sem ranking externo (Valve/vlr.gg): a classificacao V-D dos confrontos
        # que a PandaScore trouxe, por liga. Nao e "oficial" nem vira prior, mas
        # e a tabela que a cena olha e a que a tela pode mostrar.
        return _classificacao_derivada(db, id_jogo, jogo, limite)

    linhas = db.execute(
        select(
            RankingExterno.regiao,
            RankingExterno.posicao,
            RankingExterno.equipe_nome,
            RankingExterno.pontos,
            RankingExterno.fonte,
            RankingExterno.id_equipe,
            DimEquipe.tag,
            DimEquipe.logo_url,
        )
        .outerjoin(DimEquipe, RankingExterno.id_equipe == DimEquipe.id_equipe)
        .where(
            RankingExterno.id_jogo == id_jogo,
            RankingExterno.data_referencia == ultima,
        )
        .order_by(RankingExterno.regiao, RankingExterno.posicao)
    ).all()

    fonte_slug = linhas[0].fonte if linhas else "vlr"
    fonte_nome, url_fonte = FONTES.get(fonte_slug, (fonte_slug, ""))

    por_regiao: dict[str | None, list[EquipeRankingOficial]] = {}
    for linha in linhas:
        regiao = por_regiao.setdefault(linha.regiao, [])
        if len(regiao) >= limite:
            continue
        regiao.append(
            EquipeRankingOficial(
                posicao=linha.posicao,
                # o scrape do vlr.gg as vezes deixa um surrogate solto num nome
                # acentuado; normaliza para nao quebrar a serializacao JSON.
                equipe_nome=linha.equipe_nome.encode("utf-8", "replace").decode("utf-8"),
                id_equipe=linha.id_equipe,
                tag=linha.tag,
                logo_url=linha.logo_url,
                pontos=linha.pontos,
            )
        )

    regioes = [
        RegiaoRanking(
            slug=slug or "global",
            nome=REGIOES.get(slug or "global", (slug or "Global").replace("-", " ").title()),
            equipes=equipes,
        )
        for slug, equipes in sorted(por_regiao.items(), key=lambda par: _ordem_regiao(par[0]))
    ]

    return RankingOficialResposta(
        jogo=jogo,
        fonte=fonte_nome,
        url_fonte=url_fonte,
        data_referencia=ultima,
        regioes=regioes,
    )


#: Janela da classificacao derivada. Cinco meses cobrem uma temporada regional
#: sem arrastar resultado de um ano atras.
_JANELA_DIAS = 150
#: Minimo de series decididas para um time entrar na tabela da liga.
_MIN_SERIES = 3


def _liga_do_torneio(torneio: str | None) -> str:
    """`LCK — Playoffs` -> `LCK`. O nome antes do travessao e a liga/regiao."""
    if not torneio:
        return "Outros"
    return torneio.split(" — ")[0].strip() or "Outros"


def _classificacao_derivada(
    db: Session, id_jogo: int, jogo: str, limite: int
) -> RankingOficialResposta:
    corte = datetime.now(timezone.utc) - timedelta(days=_JANELA_DIAS)

    base = (
        select(
            AgendaPartida.torneio,
            AgendaPartida.id_equipe_a,
            AgendaPartida.id_equipe_b,
            AgendaPartida.equipe_a_nome,
            AgendaPartida.equipe_b_nome,
            AgendaPartida.vitoria_a,
            AgendaPartida.inicio_previsto,
        )
        .where(
            AgendaPartida.id_jogo == id_jogo,
            AgendaPartida.vitoria_a.is_not(None),
            AgendaPartida.inicio_previsto >= corte,
        )
    )
    linhas = db.execute(restringir_recorte(db, base)).all()
    if not linhas:
        raise HTTPException(
            status_code=404,
            detail=f"sem confrontos recentes para classificar {jogo!r}",
        )

    # (liga, chave_time) -> {nome, id_equipe, v, d, ultimo}
    tabela: dict[tuple[str, object], dict] = {}
    for lin in linhas:
        liga = _liga_do_torneio(lin.torneio)
        for id_eq, nome, venceu in (
            (lin.id_equipe_a, lin.equipe_a_nome, lin.vitoria_a is True),
            (lin.id_equipe_b, lin.equipe_b_nome, lin.vitoria_a is False),
        ):
            chave = id_eq if id_eq is not None else f"nome:{nome}"
            reg = tabela.setdefault(
                (liga, chave),
                {"nome": nome, "id_equipe": id_eq, "v": 0, "d": 0},
            )
            reg["v" if venceu else "d"] += 1

    # escudo/tag por id_equipe
    ids = {r["id_equipe"] for r in tabela.values() if r["id_equipe"] is not None}
    meta = {
        e.id_equipe: (e.tag, e.logo_url)
        for e in db.execute(
            select(DimEquipe.id_equipe, DimEquipe.tag, DimEquipe.logo_url).where(
                DimEquipe.id_equipe.in_(ids)
            )
        )
    } if ids else {}

    por_liga: dict[str, list[dict]] = {}
    for (liga, _chave), reg in tabela.items():
        if reg["v"] + reg["d"] < _MIN_SERIES:
            continue
        por_liga.setdefault(liga, []).append(reg)

    if not por_liga:
        raise HTTPException(
            status_code=404,
            detail=f"confrontos de {jogo!r} ainda rasos para uma classificação",
        )

    regioes: list[RegiaoRanking] = []
    for liga, times in sorted(por_liga.items(), key=lambda p: -len(p[1])):
        times.sort(key=lambda r: (-(r["v"] / (r["v"] + r["d"])), -r["v"]))
        equipes = []
        for pos, reg in enumerate(times[:limite], start=1):
            tag, logo = meta.get(reg["id_equipe"], (None, None))
            total = reg["v"] + reg["d"]
            equipes.append(
                EquipeRankingOficial(
                    posicao=pos,
                    equipe_nome=reg["nome"],
                    id_equipe=reg["id_equipe"],
                    tag=tag,
                    logo_url=logo,
                    pontos=round(100 * reg["v"] / total),
                    vitorias=reg["v"],
                    derrotas=reg["d"],
                )
            )
        regioes.append(
            RegiaoRanking(slug=_slug(liga), nome=liga, equipes=equipes)
        )

    return RankingOficialResposta(
        jogo=jogo,
        fonte="Classificação",
        url_fonte="",
        data_referencia=date.today(),
        regioes=regioes,
        derivado=True,
    )


def _slug(texto: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-") or "liga"
