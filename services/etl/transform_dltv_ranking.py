"""Ranking mundial de Dota 2 do DLTV -> linhas de ranking.

Dota 2 não tem ranking oficial: a Valve encerrou o Dota Pro Circuit depois de
2023 e não publica classificação desde então. O DLTV (dltv.org/ranking) mantém
um ranking mundial de times profissionais - soma ponderada de pontos por
resultado nos últimos ~3 meses, com peso maior para as partidas recentes e um
núcleo de três jogadores ativos. É a referência que a cena usa, no lugar que o
vlr.gg ocupa em Valorant.

Lista global única (sem regiões), renderizada no servidor. Cada linha:

    <div class="ranking__list-case__item">
      <div class="item__info-num">#1</div>
      <a class="item__info-logo" data-theme-dark="https://s3.dltv.org/...webp"></a>
      <div class="item__info-team__name">
        <div class="name">PARIVISION</div>
        <div class="points">(1,849 Pontos)</div>
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FONTE = "dltv"
JOGO = "dota2"
REGIAO = "global"


@dataclass
class LinhaRanking:
    equipe_nome: str
    posicao: int
    pontos: int | None
    logo_url: str | None = None


@dataclass
class ResultadoRanking:
    data_referencia: date
    linhas: list[LinhaRanking] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.linhas)


def parse_ranking(html: str) -> list[LinhaRanking]:
    if not isinstance(html, str) or "ranking__list-case__item" not in html:
        return []

    sopa = BeautifulSoup(html, "html.parser")
    linhas: list[LinhaRanking] = []
    vistos: set[str] = set()
    for item in sopa.select(".ranking__list-case__item"):
        num = item.select_one(".item__info-num")
        nome_el = item.select_one(".item__info-team__name .name")
        if num is None or nome_el is None:
            continue
        achado = re.search(r"\d+", num.get_text())
        if achado is None:
            continue

        nome = nome_el.get_text(strip=True)
        if not nome or nome.lower() in vistos:
            continue
        vistos.add(nome.lower())

        pontos = None
        pts_el = item.select_one(".item__info-team__name .points")
        if pts_el is not None:
            m_pts = re.search(r"[\d,.]+", pts_el.get_text())
            if m_pts:
                try:
                    pontos = int(m_pts.group().replace(",", "").replace(".", ""))
                except ValueError:
                    pontos = None

        logo = None
        logo_el = item.select_one(".item__info-logo")
        if logo_el is not None:
            logo = logo_el.get("data-theme-dark") or logo_el.get("data-theme-light")

        linhas.append(
            LinhaRanking(
                equipe_nome=nome[:120],
                posicao=int(achado.group()),
                pontos=pontos,
                logo_url=logo,
            )
        )

    if not linhas:
        logger.info("ranking do DLTV sem linhas")
    return linhas
