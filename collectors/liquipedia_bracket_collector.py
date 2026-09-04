"""Coletor de resultados via bracket, para os torneios que a agenda ja conhece.

**A lista de torneios nao e escrita a mao - ela cresce sozinha.** Cada vez que
`Liquipedia:Matches` (o ticker) mostra um confronto de um torneio novo, o nome
dele fica gravado em `agenda_partida.torneio`. Este coletor le esses nomes
distintos e pede a pagina de CADA UM: e o mesmo texto que a Liquipedia usa
como titulo da pagina, entao nao ha reconciliacao nenhuma a fazer - o nome que
o ticker deu E o titulo da pagina do bracket.

O efeito e cumulativo: quanto mais o ticker roda, mais torneios a lista
conhece, e mais bracket ha para expandir. Um torneio que o ticker nunca
mencionou tambem nao tem como aparecer aqui - nao existe fonte para "todos os
torneios que existem", so para os que ja vimos de relance.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from sqlalchemy import select

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from db.models import AgendaPartida, DimJogo
from db.session import session_scope
from etl.load_liquipedia import carregar
from etl.transform_liquipedia import ResultadoAgenda
from etl.transform_liquipedia_bracket import ENDPOINT_BRACKET, FONTE, transformar

logger = logging.getLogger(__name__)

URL_API = "https://liquipedia.net/{wiki}/api.php"


def torneios_conhecidos(jogo: str) -> list[str]:
    """Os nomes de torneio distintos que ja apareceram na agenda deste jogo."""
    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == jogo))
        if id_jogo is None:
            return []
        linhas = sessao.scalars(
            select(AgendaPartida.torneio)
            .where(AgendaPartida.id_jogo == id_jogo, AgendaPartida.torneio.is_not(None))
            .distinct()
        )
        return [t for t in linhas if t]


class LiquipediaBracketCollector(BaseCollector[ResultadoAgenda]):
    """Le o bracket de cada torneio conhecido de uma wiki."""

    fonte = FONTE

    def __init__(
        self,
        raw_storage: Any,
        settings: Settings | None = None,
        wiki: str = "dota2",
        torneios: Sequence[str] | None = None,
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.wiki = wiki
        # `None` = descobre sozinho pelo que a agenda ja registrou. Passar a
        # lista explicita serve para testes e para coletar so um recorte.
        self.torneios = list(torneios) if torneios is not None else torneios_conhecidos(wiki)
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

    @property
    def _url(self) -> str:
        return URL_API.format(wiki=self.wiki)

    def collect(self) -> list[RawRecord]:
        registros: list[RawRecord] = []
        for torneio in self.torneios:
            try:
                dados = self.client.get_json(
                    self._url,
                    params={
                        "action": "parse",
                        "format": "json",
                        "page": torneio,
                        "prop": "text",
                    },
                )
            except Exception as exc:  # noqa: BLE001 - um torneio nao derruba os outros
                self.falhas += 1
                logger.warning(
                    "bracket de um torneio falhou",
                    extra={
                        "wiki": self.wiki,
                        "torneio": torneio,
                        "erro": f"{type(exc).__name__}: {exc}",
                    },
                )
                continue

            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    # A wiki entra no endpoint pelo mesmo motivo da Fase 12:
                    # sem isso, os payloads de todas as wikis cairiam no
                    # mesmo caminho de `data/raw/` e um sobrescreveria o
                    # outro.
                    endpoint=f"{ENDPOINT_BRACKET}/{self.wiki}",
                    identificador=torneio,
                    payload=dados,
                )
            )

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoAgenda:
        partidas = []
        vistos: set[str] = set()

        for registro in registros:
            if registro.fonte != self.fonte or not registro.endpoint.startswith(
                ENDPOINT_BRACKET
            ):
                continue
            # `identificador` guarda o nome do torneio - e o parametro que
            # `transformar()` precisa, porque o bracket nao repete o nome do
            # torneio em cada partida.
            for partida in transformar(registro.payload, registro.identificador).partidas:
                if partida.id_externo in vistos:
                    continue
                vistos.add(partida.id_externo)
                partidas.append(partida)

        return ResultadoAgenda(partidas=partidas)

    def load(self, resultado: ResultadoAgenda) -> int:
        return carregar(resultado, jogo=self.wiki)

    def close(self) -> None:
        self.client.close()
