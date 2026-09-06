"""Ranking de equipes de Valorant do vlr.gg, para o PRIOR do modelo de confronto.

O `ml/confronto` estima a forca de cada time so dos confrontos que coletamos.
Com 131 equipes e ~210 confrontos, cada time tem tres partidas em media - e um
time novo fica preso perto de 50%. Em Counter-Strike a Valve publica um ranking
oficial que o modelo usa como prior (Fase 15); Valorant nao tinha equivalente.

O vlr.gg publica um rating por regiao (`/rankings/<regiao>`), estilo ELO
(~1000-2000), atualizado quase toda semana. Este coletor raspa as regioes que
importam para o nosso historico e grava um snapshot em `ranking_externo`
(`fonte="vlr"`), do mesmo jeito que o `valve-standings` faz para CS. O
`_carregar_ratings_externos` do modelo ja e generico - so precisou trocar a
fonte fixa por um mapa jogo -> fonte.

**Regioes.** As oito que cobrem o VCT e a maior parte do tier-2. Uma regiao
nova (a Valorant reorganiza os circuitos) entra editando `REGIOES`.

**Cadencia.** Semanal. O rating do vlr.gg nao muda de hora em hora, e guardar um
snapshot por semana ja da a serie que a validacao walk-forward precisa (o prior
point-in-time: prever uma partida de julho usa o ranking de julho).
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Sequence

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import get_settings

logger = logging.getLogger(__name__)

JOGO = "valorant"
BASE = "https://www.vlr.gg/rankings"

#: Slug de cada regiao no vlr.gg. As oito com peso no cenario.
REGIOES = (
    "north-america",
    "europe",
    "brazil",
    "korea",
    "china",
    "asia-pacific",
    "la-s",
    "la-n",
)

#: Um item do ranking: `<div class="... rank-item ...">
#:   <div class="rank-item-rank-num"> 1 </div> ...
#:   <a href="/team/120/..." data-sort-value="100 Thieves" class="rank-item-team ...">
#:   <div data-sort-value="2000" class="rank-item-rating"> 2000`
_ITEM = re.compile(
    r'rank-item-rank-num"\s*>\s*(?P<pos>\d+)\s*</div>.*?'
    r'data-sort-value="(?P<nome>[^"]+)"\s+class="rank-item-team\b.*?'
    r'data-sort-value="(?P<pontos>\d+)"\s+class="rank-item-rating"',
    re.S,
)


@dataclass
class LinhaRanking:
    equipe_nome: str
    posicao: int
    pontos: int
    regiao: str


@dataclass
class ResultadoRankingVlr:
    data_referencia: date
    linhas: list[LinhaRanking] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.linhas)


class VlrRankingsCollector(BaseCollector[ResultadoRankingVlr]):
    """Snapshot do rating de equipes de Valorant do vlr.gg."""

    fonte = "vlr_rankings"

    def collect(self) -> list[RawRecord]:
        settings = get_settings()
        cliente = RateLimitedClient(
            nome="vlr",
            intervalo_minimo=settings.liquipedia_rate_limit_seconds,
            max_retries=settings.http_max_retries,
            timeout=settings.http_timeout_seconds,
            user_agent="playdb-tcc/0.1 (+https://playdb.info)",
        )
        registros: list[RawRecord] = []
        for regiao in REGIOES:
            url = f"{BASE}/{regiao}"
            try:
                pagina = cliente.get_text(url)
            except Exception as exc:  # noqa: BLE001 - uma regiao fora nao leva as outras
                self.logger.warning(
                    "regiao do vlr rankings falhou",
                    extra={"regiao": regiao, "erro": str(exc)},
                )
                continue
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint="/rankings",
                    identificador=regiao,
                    payload=pagina,
                )
            )
        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoRankingVlr:
        vistos: set[str] = set()
        linhas: list[LinhaRanking] = []
        for registro in registros:
            if not isinstance(registro.payload, str):
                continue
            for m in _ITEM.finditer(registro.payload):
                nome = html.unescape(m.group("nome")).strip()
                if not nome or nome.lower() in vistos:
                    continue
                vistos.add(nome.lower())
                linhas.append(
                    LinhaRanking(
                        equipe_nome=nome[:120],
                        posicao=int(m.group("pos")),
                        pontos=int(m.group("pontos")),
                        regiao=registro.identificador,
                    )
                )
        return ResultadoRankingVlr(
            data_referencia=datetime.now(timezone.utc).date(),
            linhas=linhas,
        )

    def load(self, dados: ResultadoRankingVlr) -> int:
        from etl.load_vlr_rankings import carregar

        return carregar(dados)
