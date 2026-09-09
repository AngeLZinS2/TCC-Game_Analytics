"""Usuarios simultaneos da plataforma Steam + o cache de nomes do Top 100.

Duas coisas de uma coleta so, porque as duas alimentam a home e as duas sao
baratas:

1. `valvesoftware.com/en/about/stats` -> `{users_online, users_ingame}`, o
   numero real da Steam (nao a soma dos jogos que monitoramos). Vira um
   snapshot em `fato_steam_online`.
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

URL_STATS = "https://www.valvesoftware.com/en/about/stats"
URL_MAIS_JOGADOS = (
    "https://api.steampowered.com/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"
)


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
    if isinstance(bruto, int):
        return bruto
    if isinstance(bruto, str):
        digitos = bruto.replace(",", "").replace(".", "").strip()
        if digitos.isdigit():
            return int(digitos)
    return None


class SteamOnlineCollector(BaseCollector[ResultadoSteamOnline]):
    """Snapshot dos usuarios simultaneos da Steam + refresh do cache de nomes."""

    fonte = "steam_online"

    def collect(self) -> list[RawRecord]:
        settings = get_settings()
        cliente = RateLimitedClient(
            nome="valve-stats",
            intervalo_minimo=settings.steam_api_rate_limit_seconds,
            max_retries=settings.http_max_retries,
            timeout=settings.http_timeout_seconds,
            user_agent="playdb-tcc/0.1 (+https://playdb.info)",
        )
        registros: list[RawRecord] = []
        try:
            try:
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint="/en/about/stats",
                        identificador="plataforma",
                        payload=cliente.get_text(URL_STATS),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - uma parte fora nao leva a outra
                self.logger.warning("stats da Valve falharam", extra={"erro": str(exc)})

            try:
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint="/GetGamesByConcurrentPlayers",
                        identificador="top100",
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
            if registro.identificador == "plataforma" and isinstance(registro.payload, str):
                try:
                    dados = json.loads(registro.payload)
                except json.JSONDecodeError:
                    self.logger.warning("stats da Valve nao vieram em JSON")
                    continue
                resultado.usuarios_online = _para_int(dados.get("users_online"))
                resultado.usuarios_em_jogo = _para_int(dados.get("users_ingame"))

            elif registro.identificador == "top100" and isinstance(registro.payload, dict):
                ranks = ((registro.payload or {}).get("response") or {}).get("ranks") or []
                resultado.top_app_ids = [
                    r["appid"] for r in ranks if isinstance(r.get("appid"), int)
                ]

        return resultado

    def load(self, dados: ResultadoSteamOnline) -> int:
        from services.etl.load_steam_online import carregar

        return carregar(dados)
