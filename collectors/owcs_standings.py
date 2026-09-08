"""Classificação oficial do OWCS, raspada da Liquipedia.

Overwatch não tem ranking oficial persistente (ver `transform_owcs_standings`).
O melhor que dá para publicar é a tabela do Stage regional corrente. Este
coletor, para cada região, pega a página do Stage mais recente que já tem
classificação e grava um snapshot em `ranking_externo` (`fonte="owcs"`).

**Temporada e Stages.** O ano vem de `date.today()`; os Stages são tentados do
3 para o 1, parando no primeiro com tabela. Entre Stages (a OWCS passa ~um mês
sem jogo regional), isso cai na tabela final do Stage anterior - a classificação
oficial mais recente. Quando nenhuma região tem dado, o coletor não grava nada
e o painel de ranking do OW some, igual ao CoD fora de temporada.

**Termos da Liquipedia**, os mesmos dos outros coletores: `Accept-Encoding:
gzip`, User-Agent que identifica o projeto, intervalo entre chamadas. Uma
rodada são ~6 a 12 chamadas a `action=parse`, no intervalo padrão de 3s.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Sequence

import requests

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from etl.transform_owcs_standings import (
    FONTE,
    JOGO,
    LinhaRanking,
    ResultadoRanking,
    parse_standings,
)

logger = logging.getLogger(__name__)

URL_API = "https://liquipedia.net/overwatch/api.php"
PAGINA = "Overwatch Champions Series/{ano}/{regiao}/{stage}"

#: Página da região na Liquipedia -> slug de região no nosso `ranking_externo`.
#: A OWCS 2025+ separa a Ásia em Japão/Coreia/Pacífico; mantemos os três.
REGIOES: dict[str, str] = {
    "NA": "north-america",
    "EMEA": "europe",
    "China": "china",
    "Japan": "japan",
    "Korea": "korea",
    "Pacific": "pacific",
}

#: Do Stage mais recente para o mais antigo. Uma temporada da OWCS tem 3 Stages;
#: parar no primeiro com tabela dá o corrente (ou, entre Stages, o último).
STAGES = ("Stage_3", "Stage_2", "Stage_1")

#: Abaixo disto a "tabela" é ruído (um round-robin tem ao menos 4 times).
_MIN_LINHAS = 4


class OwcsStandingsCollector(BaseCollector[ResultadoRanking]):
    """Snapshot da classificação do Stage corrente do OWCS, por região."""

    fonte = FONTE

    def __init__(self, raw_storage: Any, settings: Settings | None = None) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.falhas = 0
        self.client = RateLimitedClient(
            nome="liquipedia",
            intervalo_minimo=self.settings.liquipedia_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
            user_agent=self.settings.liquipedia_user_agent,
        )
        self.client.session.headers.update({"Accept-Encoding": "gzip"})

    def _texto_renderizado(self, ano: int, regiao_pg: str, stage: str) -> str | None:
        parametros = {
            "action": "parse",
            "format": "json",
            "page": PAGINA.format(ano=ano, regiao=regiao_pg, stage=stage),
            "prop": "text",
            "redirects": "1",
        }
        try:
            corpo = self.client.get_json(URL_API, parametros)
        except (requests.RequestException, ValueError) as exc:
            self.falhas += 1
            self.logger.warning(
                "falha ao buscar página do OWCS",
                extra={"regiao": regiao_pg, "stage": stage, "erro": str(exc)},
            )
            return None
        if isinstance(corpo, dict) and corpo.get("error"):
            # página inexistente (Stage ainda não criado) - normal, não é falha
            return None
        try:
            return corpo["parse"]["text"]["*"]
        except (KeyError, TypeError):
            return None

    def collect(self) -> list[RawRecord]:
        ano = date.today().year
        registros: list[RawRecord] = []
        for regiao_pg, slug in REGIOES.items():
            for stage in STAGES:
                html = self._texto_renderizado(ano, regiao_pg, stage)
                if html is None:
                    continue
                if len(parse_standings(html, slug)) < _MIN_LINHAS:
                    continue
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint=f"standings/{slug}",
                        identificador=f"{slug}:{ano}:{stage}",
                        payload=html,
                    )
                )
                break
        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoRanking:
        linhas: list[LinhaRanking] = []
        for registro in registros:
            if registro.fonte != self.fonte or not isinstance(registro.payload, str):
                continue
            slug = registro.endpoint.removeprefix("standings/")
            linhas.extend(parse_standings(registro.payload, slug))
        return ResultadoRanking(
            data_referencia=datetime.now(timezone.utc).date(), linhas=linhas
        )

    def load(self, dados: ResultadoRanking) -> int:
        from etl.load_owcs_standings import carregar

        return carregar(dados)

    def close(self) -> None:
        self.client.close()
