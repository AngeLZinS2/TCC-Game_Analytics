"""Coletor das paginas de equipe da Liquipedia, pelo wikitexto.

Duas chamadas de tipos diferentes, nesta ordem:

1. `action=query&list=categorymembers` sobre `Category:Teams` - o indice. E
   barato (500 titulos por resposta, sem conteudo) e diz quem existe.
2. `action=query&prop=revisions&rvsection=0` em lote - o conteudo. A MediaWiki
   aceita ate 50 titulos por chamada, e `rvsection=0` traz so a secao inicial,
   onde fica o infobox.

**Por que `rvsection=0` e nao a pagina inteira.** Medido: 20 paginas de equipe
completas pesam 126,6 KB; so a secao 0, 13,3 KB. Sao 10% do trafego para 100% do
dado que interessa - o resto e historico de line-up, resultados e referencias.

**Por que a categoria e nao uma lista escrita a mao.** `Category:Teams` tem 962
equipes e e mantida pelos editores da wiki. Uma lista nossa nasceria
desatualizada, e a primeira equipe nova que aparecesse ficaria de fora sem
ninguem notar.

**Termos de uso**, os mesmos do outro coletor: `Accept-Encoding: gzip`,
User-Agent que identifica o projeto, e intervalo entre chamadas. Uma rodada
completa sao ~23 chamadas (3 de indice + 20 de conteudo), cerca de 70 segundos
no intervalo padrao.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator, Sequence

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from etl.load_liquipedia_wiki import carregar
from etl.transform_liquipedia_wiki import (
    CATEGORIA_EQUIPES,
    ENDPOINT_EQUIPES,
    FONTE,
    ResultadoEquipes,
    transformar,
)

logger = logging.getLogger(__name__)

URL_API = "https://liquipedia.net/{wiki}/api.php"

#: Titulos por chamada de conteudo. E o teto da MediaWiki para clientes sem
#: privilegio de bot; pedir mais faz a API truncar em silencio.
TITULOS_POR_LOTE = 50

#: Titulos por pagina do indice.
INDICE_POR_PAGINA = 500


class LiquipediaWikiCollector(BaseCollector[ResultadoEquipes]):
    """Equipes da Liquipedia, com o `teamid` que liga a OpenDota."""

    fonte = FONTE

    def __init__(
        self,
        raw_storage: Any,
        settings: Settings | None = None,
        wiki: str = "dota2",
        limite_equipes: int | None = None,
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.wiki = wiki
        self.limite_equipes = limite_equipes
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
        self.client.session.headers.update(
            {"Accept-Encoding": "gzip", "Accept": "application/json"}
        )

    @property
    def _url(self) -> str:
        return URL_API.format(wiki=self.wiki)

    def _titulos(self) -> list[str]:
        """Percorre o indice da categoria e devolve os titulos das paginas."""
        titulos: list[str] = []
        continuar: str | None = None

        while True:
            params: dict[str, Any] = {
                "action": "query",
                "format": "json",
                "list": "categorymembers",
                "cmtitle": CATEGORIA_EQUIPES,
                "cmlimit": INDICE_POR_PAGINA,
                # Namespace 0 = artigo. Sem isto viriam subcategorias e paginas
                # de discussao, que nao tem infobox.
                "cmnamespace": 0,
            }
            if continuar:
                params["cmcontinue"] = continuar

            dados = self.client.get_json(self._url, params=params)
            membros = (dados.get("query") or {}).get("categorymembers") or []
            titulos.extend(m["title"] for m in membros if m.get("title"))

            if self.limite_equipes and len(titulos) >= self.limite_equipes:
                return titulos[: self.limite_equipes]

            continuar = (dados.get("continue") or {}).get("cmcontinue")
            if not continuar:
                return titulos

    def _lotes(self, titulos: Sequence[str]) -> Iterator[list[str]]:
        for inicio in range(0, len(titulos), TITULOS_POR_LOTE):
            yield list(titulos[inicio : inicio + TITULOS_POR_LOTE])

    def collect(self) -> list[RawRecord]:
        titulos = self._titulos()
        logger.info(
            "indice de equipes lido",
            extra={"fonte": self.fonte, "titulos": len(titulos)},
        )

        registros: list[RawRecord] = []
        for numero, lote in enumerate(self._lotes(titulos), start=1):
            try:
                dados = self.client.get_json(
                    self._url,
                    params={
                        "action": "query",
                        "format": "json",
                        "prop": "revisions",
                        "rvslots": "main",
                        "rvprop": "content",
                        "rvsection": 0,
                        "titles": "|".join(lote),
                    },
                )
            except Exception as exc:  # noqa: BLE001 - um lote nao derruba a coleta
                self.falhas += 1
                logger.warning(
                    "lote de equipes falhou",
                    extra={
                        "fonte": self.fonte,
                        "lote": numero,
                        "erro": f"{type(exc).__name__}: {exc}",
                    },
                )
                continue

            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=f"{ENDPOINT_EQUIPES}/{self.wiki}",
                    identificador=f"lote-{numero:03d}",
                    payload=dados,
                )
            )

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoEquipes:
        equipes = []
        vistos: set[int] = set()

        for registro in registros:
            # Ver o comentario gemeo em `liquipedia_collector.py`: a fonte e a
            # mesma, o endpoint e que separa agenda de equipes.
            if registro.fonte != self.fonte or not registro.endpoint.startswith(
                ENDPOINT_EQUIPES
            ):
                continue
            for equipe in transformar(registro.payload).equipes:
                if equipe.id_externo in vistos:
                    continue
                vistos.add(equipe.id_externo)
                equipes.append(equipe)

        return ResultadoEquipes(equipes=equipes)

    def load(self, resultado: ResultadoEquipes) -> int:
        return carregar(resultado, jogo=self.wiki)

    def close(self) -> None:
        self.client.close()
