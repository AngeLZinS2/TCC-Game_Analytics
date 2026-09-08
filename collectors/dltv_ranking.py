"""Ranking mundial de Dota 2: o DLTV, no lugar do ranking oficial que não existe.

A Valve encerrou o Dota Pro Circuit depois de 2023 e não publica classificação.
O DLTV (dltv.org/ranking) mantém o ranking mundial que a cena acompanha. Uma
página, lista global única; `requests` + UA de browser responde 200 de
datacenter, sem Cloudflare.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Sequence

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import get_settings
from etl.transform_dltv_ranking import (
    FONTE,
    JOGO,
    ResultadoRanking,
    parse_ranking,
)

logger = logging.getLogger(__name__)

URL = "https://dltv.org/ranking"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class DltvRankingCollector(BaseCollector[ResultadoRanking]):
    """Snapshot do ranking mundial de Dota 2 do DLTV."""

    fonte = FONTE

    def collect(self) -> list[RawRecord]:
        settings = get_settings()
        cliente = RateLimitedClient(
            nome="dltv",
            intervalo_minimo=2.0,
            max_retries=settings.http_max_retries,
            timeout=settings.http_timeout_seconds,
            user_agent=_UA,
        )
        try:
            html = cliente.get_text(URL)
        finally:
            cliente.close()
        return [
            RawRecord(
                fonte=self.fonte,
                endpoint="ranking",
                identificador=date.today().isoformat(),
                payload=html,
            )
        ]

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoRanking:
        linhas: list[Any] = []
        for registro in registros:
            if registro.fonte != self.fonte or not isinstance(registro.payload, str):
                continue
            linhas.extend(parse_ranking(registro.payload))
        return ResultadoRanking(data_referencia=date.today(), linhas=linhas)

    def load(self, dados: ResultadoRanking) -> int:
        from etl.load_dltv_ranking import carregar

        return carregar(dados)
