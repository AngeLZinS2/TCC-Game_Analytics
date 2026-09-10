"""Cenario de LoL profissional — classificacao por split e elencos.

Complementa o `lolesports.py` (que so pega o detalhe AO VIVO das partidas):
aqui e o dado estavel do split — a tabela de classificacao (`getStandings`) e
o elenco de cada time (`getTeams`). Tudo da API oficial gratuita
`esports-api.lolesports.com` com a chave publica.

Fluxo por rodada (roda a cada 12h):
1. `getLeagues` -> filtra as ligas de `LIGAS_TIER1`.
2. por liga: `getTournamentsForLeague` -> o torneio corrente (contem hoje, ou
   o de maior `endDate` recente).
3. `getStandings` -> a secao com classificacao (V-D por time).
4. `getTeams` de cada time visto na classificacao -> o elenco.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Sequence

from services.collectors.base import BaseCollector, RawRecord
from services.collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from services.collectors.lolesports import CHAVE_API, ESPORTS_API, LIGAS_TIER1
from services.etl.transform_lol_cenario import (
    ENDPOINT_STANDINGS,
    ENDPOINT_TEAM,
    FONTE,
    ResultadoLolCenario,
    transformar,
)

logger = logging.getLogger(__name__)

#: Quanto tempo depois do fim de um torneio ainda vale mostrar a classificacao
#: final dele (entre splits a liga passa ~um mes sem jogo).
JANELA_TORNEIO_DIAS = 40


class LolCenarioCollector(BaseCollector[ResultadoLolCenario]):
    """Snapshot da classificacao + elenco das ligas de LoL de tier 1."""

    fonte = FONTE

    def __init__(self, raw_storage: Any, settings: Settings | None = None) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.falhas = 0
        self.client = RateLimitedClient(
            nome="lolesports-cenario",
            intervalo_minimo=1.0,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
            user_agent="playdb-tcc/0.1 (+https://playdb.info)",
        )

    def _get(self, caminho: str, params: dict[str, Any]) -> Any:
        return self.client.get_json(
            f"{ESPORTS_API}/{caminho}",
            params={"hl": "en-US", **params},
            headers={"x-api-key": CHAVE_API},
        )

    def _torneio_corrente(self, league_id: str) -> str | None:
        try:
            dados = self._get(
                "getTournamentsForLeague", {"leagueId": league_id}
            )
        except Exception as exc:  # noqa: BLE001
            self.falhas += 1
            self.logger.warning(
                "getTournamentsForLeague falhou",
                extra={"league_id": league_id, "erro": str(exc)},
            )
            return None
        ligas = (dados or {}).get("data", {}).get("leagues") or []
        torneios = ligas[0].get("tournaments") if ligas else []
        hoje = date.today()
        corrente: tuple[str, str] | None = None
        for t in torneios or []:
            tid = t.get("id")
            fim = t.get("endDate") or ""
            inicio = t.get("startDate") or ""
            if not tid or not fim:
                continue
            if inicio <= hoje.isoformat() <= fim:
                return tid
            if fim >= (hoje - timedelta(days=JANELA_TORNEIO_DIAS)).isoformat():
                if corrente is None or fim > corrente[1]:
                    corrente = (tid, fim)
        return corrente[0] if corrente else None

    def collect(self) -> list[RawRecord]:
        registros: list[RawRecord] = []
        try:
            dados = self._get("getLeagues", {})
        except Exception as exc:  # noqa: BLE001
            self.falhas += 1
            self.logger.warning("getLeagues falhou", extra={"erro": str(exc)})
            return []

        ligas = (dados or {}).get("data", {}).get("leagues") or []
        slugs_time: set[str] = set()

        for liga in ligas:
            slug = (liga.get("slug") or "").lower()
            if slug not in LIGAS_TIER1:
                continue
            tid = self._torneio_corrente(liga.get("id"))
            if tid is None:
                continue
            try:
                standings = self._get("getStandings", {"tournamentId": tid})
            except Exception as exc:  # noqa: BLE001
                self.falhas += 1
                self.logger.warning(
                    "getStandings falhou", extra={"slug": slug, "erro": str(exc)}
                )
                continue
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=ENDPOINT_STANDINGS,
                    identificador=slug,
                    payload=standings,
                )
            )
            for st in (standings or {}).get("data", {}).get("standings") or []:
                for stage in st.get("stages") or []:
                    for sec in stage.get("sections") or []:
                        for rk in sec.get("rankings") or []:
                            for time in rk.get("teams") or []:
                                if time.get("slug"):
                                    slugs_time.add(time["slug"])

        for slug in sorted(slugs_time):
            try:
                time = self._get("getTeams", {"id": slug})
            except Exception as exc:  # noqa: BLE001
                self.falhas += 1
                self.logger.warning(
                    "getTeams falhou", extra={"slug": slug, "erro": str(exc)}
                )
                continue
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=ENDPOINT_TEAM,
                    identificador=slug,
                    payload=time,
                )
            )

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoLolCenario:
        return transformar(registros)

    def load(self, dados: ResultadoLolCenario) -> int:
        from services.etl.load_lol_cenario import carregar

        return carregar(dados)

    def close(self) -> None:
        self.client.close()
