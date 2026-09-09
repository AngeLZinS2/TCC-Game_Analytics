"""Classificação de um Stage do OWCS (Liquipedia) -> linhas de ranking.

A Overwatch não tem ranking oficial persistente. Desde 2025 a OWCS largou os
pontos de temporada: o que existe é a tabela de cada *Stage* regional, um
round-robin que zera quando o Stage seguinte começa. Não há equivalente ao
rating do vlr.gg (o GosuGamers, que fazia esse papel para OW, parou de
atualizar) nem ao SI Points do R6.

O que dá para publicar é essa tabela, do jeito que a Liquipedia renderiza a
partir do LPDB. Cada página `.../<REGIÃO>/Stage_N` traz um ou mais blocos
`div.group-table-results` - um por semana da temporada, o mesmo round-robin
recalculado. O último bloco é a classificação corrente; é o que este parser lê.

    div.group-table-results
      div.group-table-result-row            (uma por equipe)
        div.group-table-cell.group-table-rank         -> "1."
        div.group-table-cell.group-table-entry        -> nome (span.team-template-text)
        div.group-table-cell.group-table-match-score  -> "5–0"  (série)
        div.group-table-cell.group-table-game-score   -> "15–2" (mapa)
        div.group-table-cell.group-table-game-diff    -> "+13"

`pontos` fica nulo de propósito: uma tabela de Stage é ordem de colocação, não
um sistema de pontos. A posição é o ranking.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FONTE = "owcs"
JOGO = "overwatch"

#: en-dash, em-dash ou hífen - a Liquipedia usa "–" no placar.
_TRACO = re.compile(r"\s*[–—-]\s*")


@dataclass
class LinhaRanking:
    equipe_nome: str
    posicao: int
    regiao: str
    #: W-L de série, só para log/depuração - não vai para `ranking_externo`.
    serie_vitorias: int | None = None
    serie_derrotas: int | None = None


@dataclass
class ResultadoRanking:
    data_referencia: date
    linhas: list[LinhaRanking] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.linhas)


def _placar(texto: str) -> tuple[int | None, int | None]:
    partes = _TRACO.split(texto.strip(), maxsplit=1)
    if len(partes) != 2:
        return None, None
    try:
        return int(partes[0]), int(partes[1])
    except ValueError:
        return None, None


def parse_standings(html: str, regiao: str) -> list[LinhaRanking]:
    """HTML renderizado da página de Stage -> linhas da última tabela.

    Devolve `[]` quando a página não tem tabela de classificação (Stage ainda
    não começou, página só com o formato) - o chamador tenta o Stage anterior.
    """
    if not isinstance(html, str) or "group-table-results" not in html:
        return []

    sopa = BeautifulSoup(html, "html.parser")
    tabelas = sopa.select("div.group-table-results")
    if not tabelas:
        return []

    linhas: list[LinhaRanking] = []
    vistos: set[str] = set()
    for row in tabelas[-1].select(".group-table-result-row"):
        celula_rank = row.select_one(".group-table-rank")
        entrada = row.select_one(".group-table-entry")
        if celula_rank is None or entrada is None:
            continue
        achado = re.search(r"\d+", celula_rank.get_text())
        if achado is None:
            continue

        nome_el = entrada.select_one(".team-template-text") or entrada
        nome = nome_el.get_text(" ", strip=True)
        if not nome or nome.lower() in vistos:
            continue
        vistos.add(nome.lower())

        placar = row.select_one(".group-table-match-score")
        vit, der = _placar(placar.get_text()) if placar else (None, None)

        linhas.append(
            LinhaRanking(
                equipe_nome=nome[:120],
                posicao=int(achado.group()),
                regiao=regiao,
                serie_vitorias=vit,
                serie_derrotas=der,
            )
        )

    if not linhas:
        logger.info("página de OWCS sem linhas de classificação", extra={"regiao": regiao})
    return linhas
