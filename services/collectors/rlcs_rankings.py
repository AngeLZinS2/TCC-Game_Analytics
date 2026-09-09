"""Ranking oficial da Rocket League: o leaderboard da RLCS no blast.tv.

A BLAST (que opera a RLCS com a Epic) publica o leaderboard oficial de pontos
por região. O estágio `world-championship` é a soma da temporada inteira -
Major 1 + Major 2 + qualifiers -, o ranking regional com que os times chegam
ao Mundial. Fora dessa janela cai em `major-2`/`major-1`.

Sete regiões (EU, NA, MENA, OCE, SAM, APAC, SSA). O ano vem de `date.today()`.
Cada região é uma página; uma que falhe não derruba as outras. Fora de
temporada (ano novo, antes do Major 1) nada casa e o coletor não grava -
mesmo comportamento do CoD e do OWCS.

`requests` + UA de browser: o blast.tv responde 200 de datacenter, sem
Cloudflare.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Sequence

from services.collectors.base import BaseCollector, RawRecord
from services.collectors.http_client import RateLimitedClient
from config import get_settings
from services.etl.transform_rlcs_rankings import (
    FONTE,
    JOGO,
    LinhaRanking,
    ResultadoRanking,
    parse_leaderboard,
)

logger = logging.getLogger(__name__)

URL = "https://blast.tv/rl/leaderboard/{ano}/{estagio}/{regiao}"

#: Slug da região no blast.tv -> slug no nosso `ranking_externo`.
REGIOES: dict[str, str] = {
    "eu": "europe",
    "na": "north-america",
    "mena": "mena",
    "oce": "oceania",
    "sam": "south-america",
    "apac": "asia-pacific",
    "ssa": "sub-saharan-africa",
}

#: Do estágio mais completo para o menos. `world-championship` acumula a
#: temporada; os Majors, só o próprio.
ESTAGIOS = ("world-championship", "major-2", "major-1")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

#: Abaixo disto não é um leaderboard de verdade.
_MIN_LINHAS = 8


class RlcsRankingsCollector(BaseCollector[ResultadoRanking]):
    """Snapshot do leaderboard de pontos da RLCS, por região."""

    fonte = FONTE

    def __init__(self, raw_storage: Any, settings: Any | None = None) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.falhas = 0
        self.client = RateLimitedClient(
            nome="blast_rl",
            intervalo_minimo=2.0,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
            user_agent=_UA,
        )

    def _pagina(self, ano: int, estagio: str, regiao: str) -> str | None:
        url = URL.format(ano=ano, estagio=estagio, regiao=regiao)
        try:
            return self.client.get_text(url)
        except Exception as exc:  # noqa: BLE001 - 404 de estágio inexistente é normal
            self.logger.debug(
                "página da RLCS indisponível",
                extra={"estagio": estagio, "regiao": regiao, "erro": str(exc)},
            )
            return None

    def collect(self) -> list[RawRecord]:
        ano = date.today().year
        registros: list[RawRecord] = []
        for regiao_bt, slug in REGIOES.items():
            for estagio in ESTAGIOS:
                html = self._pagina(ano, estagio, regiao_bt)
                if html is None:
                    continue
                if len(parse_leaderboard(html, slug)) < _MIN_LINHAS:
                    continue
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint=f"leaderboard/{slug}",
                        identificador=f"{slug}:{ano}:{estagio}",
                        payload=html,
                    )
                )
                break
        if not registros:
            self.falhas += 1
        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoRanking:
        linhas: list[LinhaRanking] = []
        for registro in registros:
            if registro.fonte != self.fonte or not isinstance(registro.payload, str):
                continue
            slug = registro.endpoint.removeprefix("leaderboard/")
            linhas.extend(parse_leaderboard(registro.payload, slug))
        return ResultadoRanking(
            data_referencia=datetime.now(timezone.utc).date(), linhas=linhas
        )

    def load(self, dados: ResultadoRanking) -> int:
        from services.etl.load_rlcs_rankings import carregar

        return carregar(dados)

    def close(self) -> None:
        self.client.close()
