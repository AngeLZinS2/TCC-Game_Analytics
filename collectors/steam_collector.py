"""Coletor do dominio catalogo/mercado (Steam).

Tres endpoints publicos, nenhum exige chave de API:

  1. store.steampowered.com/api/appdetails      -> catalogo (nome, genero, preco)
  2. store.steampowered.com/appreviews/<id>     -> resumo agregado + o texto
                                                  das avaliacoes recentes
  3. api.steampowered.com/.../GetNumberOfCurrentPlayers -> jogadores simultaneos

(1) e (2) moram no mesmo host e compartilham o mesmo balde de rate limit
(~200 requisicoes / 5 min por IP), por isso usam o MESMO cliente HTTP: o
throttle precisa valer para a soma das duas chamadas.

STEAM_API_KEY fica reservada para endpoints autenticados de fases futuras.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence

import requests

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from etl.load_steam import carregar
from etl.transform_steam import (
    ENDPOINT_AVALIACOES,
    ENDPOINT_DETALHES,
    ENDPOINT_JOGADORES,
    ENDPOINT_NOTICIAS,
    ENDPOINT_STEAMSPY,
    FONTE,
    ResultadoSteam,
    transformar,
)

logger = logging.getLogger(__name__)

URL_APPDETAILS = "https://store.steampowered.com/api/appdetails"
URL_APPREVIEWS = "https://store.steampowered.com/appreviews/{app_id}"
URL_JOGADORES = (
    "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
)
URL_NOTICIAS = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
URL_STEAMSPY = "https://steamspy.com/api.php"

#: Quantas noticias pedir por jogo. O feed muda em dias; 5 cobre as ultimas
#: atualizacoes sem inchar o payload.
NOTICIAS_POR_APP = 5
# ISteamApps/GetAppList foi deprecado. O endpoint atual e IStoreService/GetAppList
# (requer STEAM_API_KEY e pagina pelo parametro last_appid).
URL_GETAPPLIST = "https://api.steampowered.com/IStoreService/GetAppList/v1/"

ARQUIVO_SEMENTE = Path(__file__).resolve().parent / "seeds" / "steam_apps.json"


def carregar_apps_semente(caminho: Path = ARQUIVO_SEMENTE) -> list[int]:
    """Le a lista fixa de app_ids monitorados."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return [int(item["app_id"]) for item in dados["apps"]]


class SteamCollector(BaseCollector[ResultadoSteam]):
    fonte = FONTE

    def __init__(
        self,
        raw_storage: Any,
        app_ids: Sequence[int] | None = None,
        settings: Settings | None = None,
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.app_ids = list(app_ids) if app_ids else carregar_apps_semente()
        self.falhas = 0

        self.store_client = RateLimitedClient(
            nome="steam-store",
            intervalo_minimo=self.settings.steam_store_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
        )
        self.api_client = RateLimitedClient(
            nome="steam-api",
            intervalo_minimo=self.settings.steam_api_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
        )
        self.spy_client = RateLimitedClient(
            nome="steamspy",
            intervalo_minimo=self.settings.steam_spy_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
        )

    # -- descoberta de apps --------------------------------------------------

    def apps_mais_jogados(self, limite: int) -> list[int]:
        """Top N do SteamSpy (jogos mais jogados nas ultimas 2 semanas)."""
        cliente = RateLimitedClient(
            nome="steamspy",
            intervalo_minimo=self.settings.steam_spy_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
        )
        try:
            dados = cliente.get_json(URL_STEAMSPY, {"request": "top100in2weeks"})
        finally:
            cliente.close()

        if not isinstance(dados, dict):
            return []
        return [int(app_id) for app_id in list(dados.keys())[:limite]]

    def todos_os_apps(
        self,
        minimo_jogadores: int = 0,
        limite: int = 0,
    ) -> list[int]:
        """Descobre todos os apps do catalogo Steam.

        Usa IStoreService/GetAppList/v1 (requer STEAM_API_KEY configurada
        em .env). Pagina automaticamente via `last_appid` ate esgotar o
        catalogo ou atingir `limite`.

        Args:
            minimo_jogadores: descarta apps com menos que este numero de
                jogadores recentes (0 = sem filtro). Requer SteamSpy.
            limite: trunca a lista final a este tamanho (0 = sem limite).

        Returns:
            Lista de app_ids; ordenada por popularidade decrescente quando
            `minimo_jogadores > 0`, caso contrario na ordem da API.

        Raises:
            RuntimeError: STEAM_API_KEY nao configurada.
        """
        if not self.settings.steam_api_key:
            raise RuntimeError(
                "STEAM_API_KEY nao configurada. "
                "Defina-a em .env para usar --all-apps.\n"
                "Gere a chave em: https://steamcommunity.com/dev/apikey"
            )

        todos_ids: list[int] = []
        last_appid = 0
        pagina = 0

        while True:
            pagina += 1
            params: dict[str, Any] = {
                "key": self.settings.steam_api_key,
                "include_games": 1,
                "include_dlc": 0,
                "include_software": 0,
                "include_videos": 0,
                "include_hardware": 0,
                "max_results": 50000,
            }
            if last_appid:
                params["last_appid"] = last_appid

            try:
                dados = self.api_client.get_json(URL_GETAPPLIST, params)
            except (requests.RequestException, ValueError) as exc:
                self.logger.warning(
                    "falha ao paginar GetAppList",
                    extra={"pagina": pagina, "erro": f"{type(exc).__name__}: {exc}"},
                )
                break

            apps = dados.get("response", {}).get("apps") or []
            if not apps:
                break  # catalogo esgotado

            novos = [
                int(a["appid"]) for a in apps if a.get("name", "").strip()
            ]
            todos_ids.extend(novos)

            self.logger.info(
                "GetAppList pagina concluida",
                extra={"pagina": pagina, "novos": len(novos), "total": len(todos_ids)},
            )

            # Verifica se ha mais paginas
            tem_mais = dados.get("response", {}).get("have_more_results", False)
            if not tem_mais:
                break

            last_appid = apps[-1]["appid"]

            # Para o laco cedo se ja temos apps suficientes para o limite
            if limite and len(todos_ids) >= limite:
                break

        self.logger.info(
            "GetAppList concluido",
            extra={"total_apps": len(todos_ids)},
        )

        if minimo_jogadores > 0:
            todos_ids = self._filtrar_por_jogadores(todos_ids, minimo_jogadores)

        if limite > 0:
            todos_ids = todos_ids[:limite]

        return todos_ids

    def _filtrar_por_jogadores(
        self, app_ids: list[int], minimo: int
    ) -> list[int]:
        """Retorna apenas os app_ids com >= `minimo` jogadores recentes.

        Usa o endpoint `all` do SteamSpy, que devolve os top-1000 jogos
        mais jogados nas ultimas 2 semanas com contagem de jogadores.
        Apps fora desse top-1000 sao descartados (ccu presumivelmente zero).
        """
        cliente = RateLimitedClient(
            nome="steamspy-all",
            intervalo_minimo=self.settings.steam_spy_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
        )
        try:
            # page=0 retorna os 1000 mais jogados (nao ha paginacao adicional
            # no plano gratuito do SteamSpy).
            dados = cliente.get_json(URL_STEAMSPY, {"request": "all", "page": 0})
        finally:
            cliente.close()

        if not isinstance(dados, dict):
            self.logger.warning("SteamSpy /all nao retornou dict; filtro ignorado")
            return app_ids

        # Mapa {app_id: players_2weeks}
        popularidade: dict[int, int] = {}
        for app_id_str, info in dados.items():
            try:
                aid = int(app_id_str)
                jogadores = int(info.get("players_2weeks") or 0)
                popularidade[aid] = jogadores
            except (ValueError, TypeError, AttributeError):
                continue

        ids_set = set(app_ids)
        filtrados = [
            aid
            for aid, jogadores in sorted(
                popularidade.items(), key=lambda x: x[1], reverse=True
            )
            if aid in ids_set and jogadores >= minimo
        ]

        self.logger.info(
            "filtro por jogadores aplicado",
            extra={
                "minimo_jogadores": minimo,
                "antes": len(app_ids),
                "depois": len(filtrados),
            },
        )
        return filtrados

    # -- BaseCollector -------------------------------------------------------

    def collect(self) -> list[RawRecord]:
        registros: list[RawRecord] = []
        total = len(self.app_ids)

        for posicao, app_id in enumerate(self.app_ids, start=1):
            self.logger.info(
                "coletando app",
                extra={"app_id": app_id, "posicao": posicao, "total": total},
            )
            registros.extend(self._coletar_app(app_id))

        return registros

    def _coletar_app(self, app_id: int) -> list[RawRecord]:
        """Uma falha isolada nao aborta a coleta dos demais apps."""
        chamadas = (
            (
                ENDPOINT_DETALHES,
                self.store_client,
                URL_APPDETAILS,
                {
                    "appids": app_id,
                    "cc": self.settings.steam_country,
                    "l": self.settings.steam_language,
                },
            ),
            (
                ENDPOINT_JOGADORES,
                self.api_client,
                URL_JOGADORES,
                {"appid": app_id},
            ),
            (
                ENDPOINT_NOTICIAS,
                self.api_client,
                URL_NOTICIAS,
                {
                    "appid": app_id,
                    "count": NOTICIAS_POR_APP,
                    "maxlength": 0,
                },
            ),
            (
                ENDPOINT_STEAMSPY,
                self.spy_client,
                URL_STEAMSPY,
                {"request": "appdetails", "appid": app_id},
            ),
        )

        registros: list[RawRecord] = self._coletar_avaliacoes(app_id)

        for endpoint, cliente, url, params in chamadas:
            try:
                payload = cliente.get_json(url, params)
            except (requests.RequestException, ValueError) as exc:
                self.falhas += 1
                self.logger.warning(
                    "falha ao coletar endpoint",
                    extra={
                        "app_id": app_id,
                        "endpoint": endpoint,
                        "erro": f"{type(exc).__name__}: {exc}",
                    },
                )
                continue

            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=endpoint,
                    identificador=str(app_id),
                    payload=payload,
                )
            )
        return registros

    def _coletar_avaliacoes(self, app_id: int) -> list[RawRecord]:
        """Pagina o endpoint de reviews pelo cursor, uma pagina por requisicao.

        A Steam devolve `cursor` para a proxima pagina. Duas condicoes de
        parada, alem do limite configurado: pagina vazia, e cursor repetido -
        quando o acervo acaba a API devolve o MESMO cursor indefinidamente, e
        sem essa checagem o laco baixaria a ultima pagina para sempre.

        O payload de cada pagina e gravado como veio. Concatenar as paginas num
        payload so antes de gravar seria normalizar antes do disco, que e
        exatamente o que o projeto nao faz.
        """
        if self.settings.steam_reviews_por_app == 0:
            return []

        registros: list[RawRecord] = []
        cursor = "*"
        cursores_vistos: set[str] = set()

        for pagina in range(self.settings.steam_reviews_paginas):
            try:
                payload = self.store_client.get_json(
                    URL_APPREVIEWS.format(app_id=app_id),
                    {
                        "json": 1,
                        "language": "all",
                        "purchase_type": "all",
                        # `recent` em vez do padrao (`all`, ordenado por
                        # utilidade): a ordem por utilidade favorece avaliacoes
                        # antigas e muito votadas, o que enviesaria a amostra.
                        "filter": "recent",
                        # Os campos agregados do `query_summary` vem iguais com
                        # ou sem texto, entao a mesma chamada serve aos dois
                        # graos - resumo do snapshot e texto das avaliacoes.
                        "num_per_page": self.settings.steam_reviews_por_app,
                        "cursor": cursor,
                    },
                )
            except (requests.RequestException, ValueError) as exc:
                self.falhas += 1
                self.logger.warning(
                    "falha ao coletar avaliacoes",
                    extra={
                        "app_id": app_id,
                        "pagina": pagina,
                        "erro": f"{type(exc).__name__}: {exc}",
                    },
                )
                break

            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=ENDPOINT_AVALIACOES,
                    identificador=str(app_id),
                    payload=payload,
                )
            )

            if not (payload.get("reviews") or []):
                break

            proximo = payload.get("cursor")
            if not proximo or proximo in cursores_vistos:
                break
            cursores_vistos.add(proximo)
            cursor = proximo

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoSteam:
        return transformar(registros, self.settings.snapshot_bucket_minutes)

    def load(self, dados: ResultadoSteam) -> int:
        return carregar(dados)

    def close(self) -> None:
        self.store_client.close()
        self.api_client.close()
        self.spy_client.close()
