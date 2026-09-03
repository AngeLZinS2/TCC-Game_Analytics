"""Coletor da agenda de partidas da Liquipedia.

E a unica fonte do projeto que responde "o que ainda vai acontecer". A OpenDota
publica partidas encerradas e o endpoint de jogos ao vivo mostra o que esta em
curso; nenhuma das duas tem calendario.

**Termos de uso.** A Liquipedia exige, e o coletor cumpre:

* `Accept-Encoding: gzip` - sem isso a API responde 406, nao 200 com dado ruim.
* User-Agent que identifique o projeto e um contato. Um UA generico e motivo de
  bloqueio, e um bloqueio aqui derruba a coleta de todo mundo que usa o mesmo IP.
* Intervalo entre chamadas. A politica pede 2s para `action=parse`; o padrao
  aqui e 3s, com folga.

Uma chamada por coleta traz a agenda inteira - a pagina `Liquipedia:Matches`
agrega os confrontos futuros de todos os torneios ativos.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import requests

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from etl.load_liquipedia import carregar
from etl.transform_liquipedia import (
    ENDPOINT_AGENDA,
    FONTE,
    PAGINA_AGENDA,
    ResultadoAgenda,
    transformar,
)

logger = logging.getLogger(__name__)

URL_API = "https://liquipedia.net/{wiki}/api.php"


class LiquipediaCollector(BaseCollector[ResultadoAgenda]):
    fonte = FONTE

    def __init__(
        self,
        raw_storage: Any,
        settings: Settings | None = None,
        wiki: str = "dota2",
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.wiki = wiki
        self.falhas = 0

        self.client = RateLimitedClient(
            nome="liquipedia",
            intervalo_minimo=self.settings.liquipedia_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
            user_agent=self.settings.liquipedia_user_agent,
        )
        # Gzip nao e otimizacao aqui, e requisito: sem o cabecalho a API
        # responde 406 com uma pagina de erro em HTML.
        self.client.session.headers.update({"Accept-Encoding": "gzip"})

    def collect(self) -> list[RawRecord]:
        parametros = {
            "action": "parse",
            "format": "json",
            "page": PAGINA_AGENDA,
            "prop": "text",
        }

        try:
            payload = self.client.get_json(
                URL_API.format(wiki=self.wiki), parametros
            )
        except (requests.RequestException, ValueError) as exc:
            self.falhas += 1
            self.logger.warning(
                "falha ao coletar agenda",
                extra={"wiki": self.wiki, "erro": f"{type(exc).__name__}: {exc}"},
            )
            return []

        return [
            RawRecord(
                fonte=self.fonte,
                # A wiki entra no endpoint: sem isso os payloads de todas
                # elas cairiam no mesmo caminho de `data/raw/` e o ultimo
                # sobrescreveria os outros.
                endpoint=f"{ENDPOINT_AGENDA}/{self.wiki}",
                identificador=self.wiki,
                payload=payload,
            )
        ]

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoAgenda:
        agenda = ResultadoAgenda()
        for registro in registros:
            # Filtra por endpoint tambem: a mesma fonte grava dois tipos de
            # payload (`matches` e `equipes`), e `ler_ultima_coleta` devolve os
            # dois juntos. Sem isto, `--from-raw liquipedia` entregaria o
            # wikitexto das equipes a este parser de HTML.
            if registro.fonte != self.fonte or not registro.endpoint.startswith(
                ENDPOINT_AGENDA
            ):
                continue
            agenda.partidas.extend(transformar(registro.payload).partidas)
        return agenda

    def load(self, dados: ResultadoAgenda) -> int:
        return carregar(dados, jogo=self.wiki)

    def close(self) -> None:
        self.client.close()
