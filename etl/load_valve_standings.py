"""Carga do ranking da Valve em `ranking_externo`, reconciliando com a dimensao.

**Reaproveita a escada de `load_liquipedia.py`.** O problema e o mesmo: casar
um nome escrito por uma fonte ("Spirit", "Natus Vincere", "The MongolZ") com o
nome que ja esta em `dim_equipe` (que veio da Liquipedia ou da OpenDota). Em
vez de duplicar `normalizar`/`_sem_enfeites`/`_resolver`, este modulo importa
essas funcoes e o mapa de equipes de la.

**Nao cria equipe.** Diferente de `load_liquipedia`, que cria o time faltante
porque a agenda e a lista autoritativa daquele jogo, aqui o que nao casar fica
so com `id_equipe` nulo. O ranking tem ~400 times; criar todos encheria a
dimensao de linhas sem partida, que `estado()` descarta de qualquer jeito. O
nome e a pontuacao continuam guardados - servem para exibir o ranking e para a
reconciliacao melhorar depois - so nao viram forca no modelo ate o time
aparecer num confronto.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import DimJogo, RankingExterno
from db.session import session_scope
from etl.load_liquipedia import _mapa_de_equipes, _resolver, normalizar
from etl.lotes import em_lotes
from etl.transform_valve_standings import FONTE, ResultadoRanking

logger = logging.getLogger(__name__)

#: O Regional Standings da Valve e de CS2. Nao ha parametro de jogo: a fonte
#: cobre um jogo so.
JOGO = "counterstrike"

#: A Valve escreve o nome curto da organizacao ("Spirit", "Vitality", "G2",
#: "9z"), enquanto `dim_equipe` costuma ter a forma longa vinda da Liquipedia
#: ("Team Spirit", "Team Vitality", "G2 Esports", "9z Team"). A escada de
#: `_resolver` corta sufixo de organizacao, mas so quando sobra nome bastante
#: ("g2esports" -> "esports" tem 7 letras, o guard exige > 9) - entao para
#: sigla curta ela nao ajuda. Aqui a reconciliacao tenta o nome com cada afixo
#: comum grudado, dos dois lados, e casa por igualdade exata contra a dimensao.
_AFIXOS_ORG = ("Team", "The", "Esports", "Gaming", "Clan", "CS", "Force")

#: O irredutivel: rebranding, sigla que nao vira o nome, nome de lineup contra
#: nome de organizacao. Chave = nome normalizado como a Valve escreve; valor =
#: nome como esta em `dim_equipe`. Cresce quando alguem olha os nao casados do
#: topo do ranking.
_APELIDOS_VALVE: dict[str, str] = {
    "ww": "WW TEAM",
}


def _resolver_valve(nome: str, mapa: dict[str, int]) -> int | None:
    """Escada de `load_liquipedia` mais os ajustes de estilo de nome da Valve."""
    achado = _resolver(nome, mapa)
    if achado is not None:
        return achado

    baixo = nome.lower().strip()
    for afixo in _AFIXOS_ORG:
        # "Spirit" -> "Team Spirit"; "G2" -> "G2 Esports"; "9z" -> "9z Team".
        for variante in (f"{afixo} {nome}", f"{nome} {afixo}"):
            achado = _resolver(variante, mapa)
            if achado is not None:
                return achado
        # o inverso: a Valve escreveu "Team X", dim_equipe tem so "X".
        if baixo.startswith(f"{afixo.lower()} "):
            achado = _resolver(nome[len(afixo) + 1:], mapa)
            if achado is not None:
                return achado
        if baixo.endswith(f" {afixo.lower()}"):
            achado = _resolver(nome[: -(len(afixo) + 1)], mapa)
            if achado is not None:
                return achado

    apelido = _APELIDOS_VALVE.get(normalizar(nome))
    if apelido:
        return mapa.get(apelido) or mapa.get(normalizar(apelido))

    return None


def carregar(resultado: ResultadoRanking, jogo: str = JOGO) -> int:
    """Persiste um snapshot do ranking, ligando cada linha a `dim_equipe`.

    Devolve quantas linhas foram gravadas. Idempotente por
    `uq_ranking_externo_snapshot`: recoletar o mesmo mes reescreve as linhas.
    """
    if resultado.data_referencia is None:
        logger.warning("ranking sem data de referencia - nada a carregar")
        return 0
    if not resultado.linhas:
        return 0

    agora = datetime.now(timezone.utc)

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == jogo))
        if id_jogo is None:
            raise RuntimeError(
                f"jogo {jogo!r} ausente em dim_jogo - rode `cli.py seed-jogos`"
            )

        mapa = _mapa_de_equipes(sessao, id_jogo)

        linhas = []
        casados = 0
        for linha in resultado.linhas:
            id_equipe = _resolver_valve(linha.equipe_nome, mapa)
            if id_equipe is not None:
                casados += 1
            linhas.append(
                {
                    "fonte": FONTE,
                    "id_jogo": id_jogo,
                    "data_referencia": resultado.data_referencia,
                    "regiao": resultado.regiao,
                    "id_equipe": id_equipe,
                    "equipe_nome": linha.equipe_nome[:120],
                    "posicao": linha.posicao,
                    "pontos": linha.pontos,
                    "coletado_em": agora,
                }
            )

        for lote in em_lotes(linhas):
            stmt = pg_insert(RankingExterno).values(lote)
            atualizaveis = {
                coluna: stmt.excluded[coluna]
                for coluna in lote[0]
                if coluna
                not in ("fonte", "id_jogo", "data_referencia", "regiao", "equipe_nome")
            }
            sessao.execute(
                stmt.on_conflict_do_update(
                    constraint="uq_ranking_externo_snapshot", set_=atualizaveis
                )
            )

    logger.info(
        "ranking externo carregado",
        extra={
            "fonte": FONTE,
            "data_referencia": resultado.data_referencia.isoformat(),
            "regiao": resultado.regiao,
            "linhas": len(linhas),
            "com_equipe_casada": casados,
        },
    )
    return len(linhas)
