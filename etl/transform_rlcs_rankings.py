"""Leaderboard oficial da RLCS (blast.tv) -> linhas de ranking.

A BLAST opera a Rocket League Championship Series com a Epic e publica o
leaderboard oficial de pontos em `blast.tv/rl/leaderboard/<ano>/<estagio>/
<regiao>`. O estágio `world-championship` traz a soma da temporada inteira
(Major 1 + Major 2 + qualifiers) - é o ranking regional oficial com que os
times chegam ao Mundial.

O leaderboard é renderizado no servidor; cada linha é um `div.group[data-active]`:

    <span class="min-w-8">#1</span>
    <img alt="Karmine Corp logo" src="https://assets.blast.tv/images/teams/...">
    <div class="min-w-12"><span>40</span><span>pts</span></div>

`pontos` pode ser negativo (penalidade) - a coluna aguenta.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FONTE = "rlcs"
JOGO = "rocketleague"

_LOGO = re.compile(r"\slogo$", re.IGNORECASE)


@dataclass
class LinhaRanking:
    equipe_nome: str
    posicao: int
    regiao: str
    pontos: int | None = None


@dataclass
class ResultadoRanking:
    data_referencia: date
    linhas: list[LinhaRanking] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.linhas)


def _inteiro(texto: str) -> int | None:
    texto = texto.strip()
    if texto.lstrip("-").isdigit():
        return int(texto)
    return None


def parse_leaderboard(html: str, regiao: str) -> list[LinhaRanking]:
    """HTML do leaderboard da região -> linhas.

    Devolve `[]` quando a página não tem leaderboard (estágio/ano ainda sem
    dado, 404) - o chamador tenta o estágio anterior.
    """
    if not isinstance(html, str) or "data-active" not in html:
        return []

    sopa = BeautifulSoup(html, "html.parser")
    linhas: list[LinhaRanking] = []
    vistos: set[str] = set()
    for row in sopa.select("div.group[data-active]"):
        celula_rank = row.find("span", class_="min-w-8")
        if celula_rank is None:
            continue
        achado = re.search(r"\d+", celula_rank.get_text())
        if achado is None:
            continue

        img = row.find("img", alt=_LOGO)
        if img is None or not img.get("alt"):
            continue
        nome = _LOGO.sub("", img["alt"]).strip()
        if not nome or nome.lower() in vistos:
            continue
        vistos.add(nome.lower())

        pontos = None
        celula_pts = row.find("div", class_="min-w-12")
        if celula_pts is not None:
            span = celula_pts.find("span")
            if span is not None:
                pontos = _inteiro(span.get_text())

        linhas.append(
            LinhaRanking(
                equipe_nome=nome[:120],
                posicao=int(achado.group()),
                regiao=regiao,
                pontos=pontos,
            )
        )

    if not linhas:
        logger.info("leaderboard da RLCS sem linhas", extra={"regiao": regiao})
    return linhas
