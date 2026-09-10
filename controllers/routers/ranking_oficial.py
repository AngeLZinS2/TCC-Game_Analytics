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
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from views.schemas import EquipeRankingOficial, RankingOficialResposta, RegiaoRanking
from models.models import DimEquipe, DimJogo, RankingExterno
from models.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/esports", tags=["esports"])

#: Como cada fonte se chama e onde o publico confere o original.
FONTES = {
    "vlr": ("vlr.gg", "https://www.vlr.gg/rankings"),
    "valve": ("Valve Regional Standings", "https://github.com/ValveSoftware/counter-strike_regional_standings"),
    "ubi_r6": (
        "R6 Esports Global Standings",
        "https://www.ubisoft.com/en-us/esports/rainbow-six/siege/global-standings",
    ),
    "owcs": (
        "OWCS (Liquipedia)",
        "https://liquipedia.net/overwatch/Overwatch_Champions_Series",
    ),
    "rlcs": ("RLCS (blast.tv)", "https://blast.tv/rl/leaderboard"),
    "dltv": ("DLTV World Ranking", "https://dltv.org/ranking"),
    "lolesports": ("LoL Esports (oficial)", "https://lolesports.com/standings"),
}

#: Nome de exibicao e ORDEM das regioes. Uma regiao fora deste mapa ainda
#: aparece (com o slug como nome), so vai para o fim da lista.
REGIOES = {
    "north-america": "América do Norte",
    "europe": "Europa",
    "brazil": "Brasil",
    "korea": "Coreia",
    "japan": "Japão",
    "china": "China",
    "pacific": "Pacífico",
    "asia-pacific": "Ásia-Pacífico",
    "mena": "MENA",
    "oceania": "Oceania",
    "south-america": "América do Sul",
    "sub-saharan-africa": "África Subsaariana",
    "la-s": "LATAM Sul",
    "la-n": "LATAM Norte",
    # LoL Esports — splits regionais (a fonte publica V-D, não rating).
    "lck": "LCK (Coreia)",
    "lpl": "LPL (China)",
    "lec": "LEC (Europa)",
    "lta-north": "LTA Norte",
    "lta-south": "LTA Sul",
    "cblol": "CBLOL (Brasil)",
    "ljl": "LJL (Japão)",
    "lcp": "LCP (Ásia-Pacífico)",
    "nacl": "NACL (Américas)",
    "international": "Internacional",
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
        # So o ranking EXTERNO oficial (Valve/vlr.gg). A classificacao derivada
        # dos nossos confrontos foi desabilitada ate haver dado suficiente e
        # confiavel - decisao do produto, 2026-09-08.
        raise HTTPException(
            status_code=404,
            detail=f"nenhum ranking oficial coletado para {jogo!r}",
        )

    linhas = db.execute(
        select(
            RankingExterno.regiao,
            RankingExterno.posicao,
            RankingExterno.equipe_nome,
            RankingExterno.pontos,
            RankingExterno.vitorias,
            RankingExterno.derrotas,
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
                vitorias=linha.vitorias,
                derrotas=linha.derrotas,
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

