"""Carga das equipes da Liquipedia em `dim_equipe`.

**O vinculo e por igualdade de inteiro, nao por semelhanca de nome.** O
`|teamid=` do `{{Infobox team}}` e o mesmo identificador que a OpenDota publica
em `radiant_team.team_id`, e que ja esta gravado em `dim_equipe.id_externo`.
Entao aqui nao ha escada de reconciliacao, nao ha `APELIDOS`, nao ha corte de
sufixo - ha um `WHERE id_externo = :teamid`.

Isso e o oposto de `load_liquipedia.py`, que casa nome de agenda com nome de
equipe e por isso precisa de toda aquela cautela. A diferenca nao e de rigor: e
que la a fonte nao publica identificador e aqui publica. Quando a fonte da a
chave, usar a chave e a unica coisa sensata.

**Equipes novas entram.** A Liquipedia conhece equipes que nunca apareceram nas
nossas partidas coletadas. Elas entram na dimensao com os metadados e sem
partida associada - o que e correto: a dimensao descreve quem existe, o fato
descreve quem jogou.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import DimEquipe, DimJogo
from db.session import session_scope
from etl.transform_liquipedia_wiki import EquipeWiki, ResultadoEquipes

logger = logging.getLogger(__name__)


def _id_do_jogo(sessao: Session, codigo: str = "dota2") -> int | None:
    return sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == codigo))


def _atualizar(equipe: DimEquipe, wiki: EquipeWiki) -> bool:
    """Aplica os metadados da wiki. Devolve se algo mudou.

    **O nome vindo da OpenDota nao e sobrescrito.** As duas fontes nomeiam a
    mesma equipe de formas diferentes ("Team Spirit" na wiki, "Team Spirit" ou
    "TSpirit" na OpenDota), e trocar o nome faria a tela de partidas mostrar um
    rotulo e o ranking outro, para a mesma linha. A wiki entra com o que a
    OpenDota nao tem; onde as duas falam, a fonte do fato manda.
    """
    antes = (
        equipe.regiao,
        equipe.pais,
        equipe.ativa,
        equipe.criada_em,
        equipe.pagina_liquipedia,
    )

    equipe.regiao = wiki.regiao
    equipe.pais = wiki.pais
    equipe.ativa = wiki.ativa
    equipe.criada_em = wiki.criada_em
    equipe.pagina_liquipedia = wiki.pagina

    return antes != (
        equipe.regiao,
        equipe.pais,
        equipe.ativa,
        equipe.criada_em,
        equipe.pagina_liquipedia,
    )


def carregar(resultado: ResultadoEquipes, jogo: str = "dota2") -> int:
    """Enriquece as equipes existentes e insere as que faltam.

    Devolve quantas linhas foram tocadas - inseridas mais atualizadas.
    """
    if not resultado.equipes:
        return 0

    with session_scope() as sessao:
        id_jogo = _id_do_jogo(sessao, jogo)
        if id_jogo is None:
            logger.warning("jogo nao encontrado na dimensao", extra={"jogo": jogo})
            return 0

        # Uma consulta so: N buscas dentro do laco seriam N idas ao Postgres
        # para 962 equipes.
        existentes = {
            equipe.id_externo: equipe
            for equipe in sessao.scalars(
                select(DimEquipe).where(DimEquipe.id_jogo == id_jogo)
            )
        }

        inseridas = atualizadas = 0

        for wiki in resultado.equipes:
            chave = wiki.id_externo
            equipe = existentes.get(chave)

            if equipe is None:
                equipe = DimEquipe(
                    id_jogo=id_jogo,
                    id_externo=chave,
                    nome=wiki.nome,
                    tag=None,
                    logo_url=None,
                )
                _atualizar(equipe, wiki)
                sessao.add(equipe)
                inseridas += 1
                continue

            if _atualizar(equipe, wiki):
                atualizadas += 1

        logger.info(
            "equipes da liquipedia carregadas",
            extra={
                "recebidas": len(resultado.equipes),
                "inseridas": inseridas,
                "atualizadas": atualizadas,
            },
        )
        return inseridas + atualizadas
