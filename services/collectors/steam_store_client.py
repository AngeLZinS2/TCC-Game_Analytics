"""Cliente isolado para o catalogo completo da Steam (`IStoreService/GetAppList`).

Ponto unico por onde a paginacao do catalogo completo passa - nenhuma outra
chamada nova ao Steam Store deve duplicar esta logica. As chamadas de
`appdetails` do fluxo ja existente (jogo monitorado -> ficha/preco) continuam
em `steam_collector.py`, sem mudanca: este cliente cobre so o indice do
catalogo (Fase 35), que e a peca que faltava.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from config import Settings, get_settings
from services.collectors.http_client import RateLimitedClient

logger = logging.getLogger(__name__)

URL_GETAPPLIST = "https://api.steampowered.com/IStoreService/GetAppList/v1/"

#: Steam nao documenta um teto oficial de resultados por chamada, mas o
#: parametro `max_results` do GetAppList aceita ate 50.000 na pratica.
MAX_RESULTS_POR_PAGINA = 50_000


class SteamStoreClient:
    """Envolve `RateLimitedClient` com a chamada de catalogo completo da Steam."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._cliente = RateLimitedClient(
            nome="steam-store-catalogo",
            intervalo_minimo=1.0 / self.settings.steam_requests_per_second,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
        )
        self._atraso_extra_s = self.settings.steam_request_delay_ms / 1000

    def listar_apps(
        self,
        last_appid: int = 0,
        if_modified_since: int | None = None,
    ) -> dict[str, Any]:
        """Uma pagina do `GetAppList` - ate `MAX_RESULTS_POR_PAGINA` apps.

        `if_modified_since` (epoch, segundos) filtra so apps modificados
        desde aquele instante - usado pelo passo incremental. `last_appid`
        pagina o resultado (0 = primeira pagina).

        Devolve o dict `response` cru da Steam:
        `{"apps": [{"appid", "name", "last_modified", "price_change_number",
        "type"?}, ...], "have_more_results": bool, "last_appid": int}`.

        Raises:
            RuntimeError: `STEAM_API_KEY` nao configurada.
        """
        if not self.settings.steam_api_key:
            raise RuntimeError(
                "STEAM_API_KEY nao configurada. Defina-a em .env para "
                "sincronizar o catalogo completo."
            )

        params: dict[str, Any] = {
            "key": self.settings.steam_api_key,
            "include_games": 1,
            "include_dlc": 0,
            "include_software": 0,
            "include_videos": 0,
            "include_hardware": 0,
            "max_results": MAX_RESULTS_POR_PAGINA,
        }
        if last_appid:
            params["last_appid"] = last_appid
        if if_modified_since:
            params["if_modified_since"] = if_modified_since

        if self._atraso_extra_s:
            time.sleep(self._atraso_extra_s)

        dados = self._cliente.get_json(URL_GETAPPLIST, params)
        return (dados or {}).get("response") or {}

    def close(self) -> None:
        self._cliente.close()

    def __enter__(self) -> SteamStoreClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
