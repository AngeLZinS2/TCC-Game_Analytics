"""Usuarios simultaneos da plataforma Steam + o cache de nomes do Top 100.

Duas coisas de uma coleta so, porque as duas alimentam a home e as duas sao
baratas:

1. Numero real de gente online na Steam (nao a soma dos jogos que
   monitoramos) -> snapshot em `fato_steam_online`. A pagina
   `valvesoftware.com/en/about` pega isso de um **WebSocket**
   (`wss://community.steam-api.com/websocket/`, feed `CommunityHeadlineStats`):
   subscreve, o primeiro `feedupdate` traz `{users_online, users_ingame}`. O
   fallback HTTP antigo (`/en/about/stats`) hoje devolve `[]` - a Valve
   empurrou tudo pro socket.
2. `ISteamChartsService/GetGamesByConcurrentPlayers` -> os 100 app_ids mais
   jogados agora. O endpoint da home serve esse ranking AO VIVO, mas a Valve
   nao manda o nome do jogo junto - so o id. Aqui a gente resolve o nome de
   quem ainda nao esta em `dim_app_steam_nome` e guarda, para o endpoint so
   fazer join.

Cadencia: ~15 min. Depois da primeira rodada quase nenhum nome novo aparece
(o Top 100 muda devagar), entao o custo de rede fica perto de duas chamadas.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from services.collectors.base import BaseCollector, RawRecord
from services.collectors.http_client import RateLimitedClient
from config import get_settings

logger = logging.getLogger(__name__)

#: Fallback HTTP - hoje devolve `[]`, mantido caso a Valve o restaure.
URL_STATS = "https://www.valvesoftware.com/en/about/stats"
URL_MAIS_JOGADOS = (
    "https://api.steampowered.com/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"
)
#: O mesmo socket que `valvesoftware.com/en/about` usa pro contador ao vivo.
WS_HEADLINE_STATS = "wss://community.steam-api.com/websocket/"
WS_FEED = "CommunityHeadlineStats"
ENDPOINT_PLATAFORMA = "plataforma"
ENDPOINT_TOP100 = "top100"


@dataclass
class ResultadoSteamOnline:
    coletado_em: datetime
    usuarios_online: int | None = None
    usuarios_em_jogo: int | None = None
    #: app_ids do Top 100 mais jogados agora, na ordem do ranking.
    top_app_ids: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return 1 if self.usuarios_online is not None else 0


def _para_int(bruto: object) -> int | None:
    """`"23,728,286"` -> `23728286`. `None` se nao der para converter."""
    if isinstance(bruto, bool):
        return None
    if isinstance(bruto, int):
        return bruto
    if isinstance(bruto, str):
        digitos = bruto.replace(",", "").replace(".", "").strip()
        if digitos.isdigit():
            return int(digitos)
    return None


def _stats_do_socket(timeout: float) -> dict | None:
    """Subscreve o feed `CommunityHeadlineStats` e devolve o primeiro
    `{users_online, users_ingame}`. `None` em qualquer erro (o coletor segue
    com o Top 100)."""
    try:
        from websockets.sync.client import connect
    except ImportError:  # pragma: no cover - websockets vem com uvicorn[standard]
        logger.warning("pacote `websockets` ausente - sem stats da plataforma")
        return None

    limite = max(5.0, min(timeout, 30.0))
    try:
        with connect(
            WS_HEADLINE_STATS,
            open_timeout=limite,
            close_timeout=5,
            user_agent_header="playdb-tcc/0.1 (+https://playdb.info)",
        ) as ws:
            ws.send(json.dumps({"message": "subscribe", "seqnum": 1, "feed": WS_FEED}))
            import time as _t

            fim = _t.monotonic() + limite
            while _t.monotonic() < fim:
                bruto = ws.recv(timeout=limite)
                msg = json.loads(bruto)
                if msg.get("message") == "feedupdate" and msg.get("feed") == WS_FEED:
                    dados = json.loads(msg.get("data") or "{}")
                    if isinstance(dados, dict):
                        return dados
    except Exception as exc:  # noqa: BLE001 - erro de socket nao derruba a coleta
        logger.warning(
            "WebSocket de stats da Steam falhou",
            extra={"erro": f"{type(exc).__name__}: {exc}"},
        )
    return None


class SteamOnlineCollector(BaseCollector[ResultadoSteamOnline]):
    """Snapshot dos usuarios simultaneos da Steam + refresh do cache de nomes."""

    fonte = "steam_online"

    def collect(self) -> list[RawRecord]:
        settings = get_settings()
        registros: list[RawRecord] = []

        stats = _stats_do_socket(settings.http_timeout_seconds)
        if stats is None:
            # Ultimo recurso: o fallback HTTP (hoje `[]`, mas de graca tentar).
            cliente_http = RateLimitedClient(
                nome="valve-stats",
                intervalo_minimo=settings.steam_api_rate_limit_seconds,
                max_retries=settings.http_max_retries,
                timeout=settings.http_timeout_seconds,
                user_agent="playdb-tcc/0.1 (+https://playdb.info)",
            )
            try:
                bruto = cliente_http.get_text(URL_STATS)
                dados = json.loads(bruto)
                if isinstance(dados, dict):
                    stats = dados
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    "fallback HTTP de stats da Valve falhou",
                    extra={"erro": f"{type(exc).__name__}: {exc}"},
                )
            finally:
                cliente_http.close()

        if stats is not None:
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint="wss:CommunityHeadlineStats",
                    identificador=ENDPOINT_PLATAFORMA,
                    payload=stats,
                )
            )

        cliente = RateLimitedClient(
            nome="valve-stats",
            intervalo_minimo=settings.steam_api_rate_limit_seconds,
            max_retries=settings.http_max_retries,
            timeout=settings.http_timeout_seconds,
            user_agent="playdb-tcc/0.1 (+https://playdb.info)",
        )
        try:
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint="/GetGamesByConcurrentPlayers",
                    identificador=ENDPOINT_TOP100,
                    payload=cliente.get_json(URL_MAIS_JOGADOS),
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("ranking de mais jogados falhou", extra={"erro": str(exc)})
        finally:
            cliente.close()
        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoSteamOnline:
        resultado = ResultadoSteamOnline(coletado_em=datetime.now(timezone.utc))

        for registro in registros:
            if registro.identificador == ENDPOINT_PLATAFORMA:
                dados = registro.payload
                if isinstance(dados, str):
                    try:
                        dados = json.loads(dados)
                    except json.JSONDecodeError:
                        self.logger.warning("stats da Steam nao vieram em JSON")
                        continue
                if not isinstance(dados, dict):
                    self.logger.warning(
                        "stats da Steam num formato inesperado",
                        extra={"tipo": type(dados).__name__},
                    )
                    continue
                resultado.usuarios_online = _para_int(dados.get("users_online"))
                resultado.usuarios_em_jogo = _para_int(dados.get("users_ingame"))

            elif registro.identificador == ENDPOINT_TOP100 and isinstance(
                registro.payload, dict
            ):
                ranks = ((registro.payload or {}).get("response") or {}).get("ranks") or []
                resultado.top_app_ids = [
                    r["appid"] for r in ranks if isinstance(r.get("appid"), int)
                ]

        return resultado

    def load(self, dados: ResultadoSteamOnline) -> int:
        from services.etl.load_steam_online import carregar

        return carregar(dados)
