"""Ranking oficial de Rainbow Six: as SI Points Standings da Ubisoft.

O `ml/confronto` de R6 tinha só a força estimada dos confrontos que a
PandaScore trouxe (~1 mês). A Ubisoft publica o ranking OFICIAL — as SI Points
Standings, que decidem quem se classifica para o Six Invitational — em
`ubisoft.com/.../global-standings`. É a mesma função do Regional Standings da
Valve para CS: um prior que já sabe algo sobre time novo.

**A fonte.** A página é Next.js e serve os dados no `__NEXT_DATA__` do próprio
HTML (`props.pageProps.pageData.standings.teams`), sem chamada extra e sem
Cloudflare — um GET com User-Agent de navegador basta. 68 times, `rank`,
`totalPoints`, logo e logo da região. É um ranking GLOBAL único (não por
região), então cai como `regiao="global"`, igual ao da Valve.

**Cadência.** Semanal. Os pontos só mudam depois de um Major/Kickoff regional
(~mensal); guardar um snapshot por semana já dá a série point-in-time que a
validação walk-forward usa.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Sequence

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import get_settings
from etl.transform_valve_standings import LinhaRanking, ResultadoRanking

logger = logging.getLogger(__name__)

FONTE = "ubi_r6"
JOGO = "rainbowsix"
URL = "https://www.ubisoft.com/en-us/esports/rainbow-six/siege/global-standings"

_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
#: UA de navegador — sem ele a Ubisoft responde 403.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _times_do_next_data(html: str) -> list[dict[str, Any]]:
    m = _NEXT_DATA.search(html)
    if not m:
        raise RuntimeError("__NEXT_DATA__ não encontrado no HTML da Ubisoft")
    dados = json.loads(m.group(1))
    times = (
        dados.get("props", {})
        .get("pageProps", {})
        .get("pageData", {})
        .get("standings", {})
        .get("teams")
    )
    if not isinstance(times, list):
        raise RuntimeError("standings.teams ausente no __NEXT_DATA__")
    return times


def transformar(registros: Sequence[RawRecord]) -> ResultadoRanking:
    resultado = ResultadoRanking(regiao="global", data_referencia=date.today())
    for registro in registros:
        if not isinstance(registro.payload, str):
            continue
        for t in _times_do_next_data(registro.payload):
            nome = (t.get("name") or "").strip()
            rank = t.get("rank")
            if not nome or not isinstance(rank, int):
                continue
            pontos = t.get("totalPoints")
            resultado.linhas.append(
                LinhaRanking(
                    posicao=rank,
                    pontos=int(pontos) if isinstance(pontos, (int, float)) else None,
                    equipe_nome=nome[:120],
                )
            )
    # A Ubisoft às vezes empata posições (dois #21); a lista já vem ordenada.
    resultado.linhas.sort(key=lambda linha: linha.posicao)
    return resultado


class UbiR6Collector(BaseCollector[ResultadoRanking]):
    """SI Points Standings oficiais de R6, da Ubisoft."""

    fonte = FONTE

    def collect(self) -> list[RawRecord]:
        settings = get_settings()
        cliente = RateLimitedClient(
            nome="ubi_r6",
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
                endpoint="global-standings",
                identificador=date.today().isoformat(),
                payload=html,
            )
        ]

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoRanking:
        return transformar(registros)

    def load(self, dados: ResultadoRanking) -> int:
        from etl.load_ubi_r6 import carregar

        return carregar(dados)
