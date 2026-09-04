"""Coletor do Regional Standings da Valve (ranking mundial de CS2).

**Sem scraping, sem chave.** A Valve versiona o ranking no GitHub como arquivos
markdown, um por mes:

    live/2026/standings_global_2026_08_03.md

Este coletor:

1. lista `live/{ano}` pela API do GitHub para descobrir os nomes de arquivo (o
   dia do mes muda a cada snapshot);
2. baixa o `standings_global_*` mais recente - ou todos, para backfill - de
   `raw.githubusercontent.com`.

So o arquivo `global` e coletado: ele tem os ~400 times com pontuacao. Os
arquivos regionais sao recortes do mesmo dado com a posicao recalculada por
regiao, e a pontuacao (que e o que o prior usa) e a mesma.

**GitHub sem autenticacao permite 60 req/hora por IP.** Uma coleta semanal gasta
2 (listar + baixar); um backfill de dois anos, ~30. O intervalo entre chamadas
e generoso so por educacao com um servico gratuito.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from etl.load_valve_standings import carregar
from etl.transform_valve_standings import (
    ENDPOINT,
    FONTE,
    ResultadoRanking,
    transformar,
)

logger = logging.getLogger(__name__)

REPO = "ValveSoftware/counter-strike_regional_standings"
URL_CONTEUDO = f"https://api.github.com/repos/{REPO}/contents/{{caminho}}"
URL_RAW = f"https://raw.githubusercontent.com/{REPO}/main/{{caminho}}"

#: A pasta com os snapshots vigentes. `live/{ano}/standings_global_*.md`.
PASTA_LIVE = "live"

#: Primeiro ano com dados no repo. Usado so no backfill (`--todos`).
ANO_INICIAL = 2024


class ValveStandingsCollector(BaseCollector[list[ResultadoRanking]]):
    """Ranking mundial de CS2 publicado pela Valve."""

    fonte = FONTE

    def __init__(
        self,
        raw_storage: Any,
        settings: Settings | None = None,
        todos: bool = False,
        ate_ano: int | None = None,
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        #: `False` = so o snapshot mais recente (o que o agendador quer).
        #: `True` = todos os meses desde `ANO_INICIAL` (backfill pontual).
        self.todos = todos
        self.ate_ano = ate_ano or _ano_atual()
        self.falhas = 0

        self.client = RateLimitedClient(
            nome="github",
            intervalo_minimo=2.0,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
            user_agent=self.settings.liquipedia_user_agent,
        )

    def _arquivos_do_ano(self, ano: int) -> list[str]:
        """Os `standings_global_*.md` de `live/{ano}`, em ordem cronologica."""
        try:
            itens = self.client.get_json(
                URL_CONTEUDO.format(caminho=f"{PASTA_LIVE}/{ano}")
            )
        except Exception as exc:  # noqa: BLE001 - ano sem pasta ainda e comum
            logger.warning(
                "listagem do ano falhou",
                extra={"ano": ano, "erro": f"{type(exc).__name__}: {exc}"},
            )
            return []

        if not isinstance(itens, list):
            return []
        nomes = [
            it["name"]
            for it in itens
            if isinstance(it, dict)
            and str(it.get("name", "")).startswith("standings_global_")
        ]
        return sorted(nomes)

    def _caminhos_a_coletar(self) -> list[str]:
        anos = (
            range(ANO_INICIAL, self.ate_ano + 1) if self.todos else (self.ate_ano,)
        )
        por_ano = {ano: self._arquivos_do_ano(ano) for ano in anos}

        if self.todos:
            return [
                f"{PASTA_LIVE}/{ano}/{nome}"
                for ano in sorted(por_ano)
                for nome in por_ano[ano]
            ]

        # So o mais recente: o ultimo nome do ano corrente; se o ano virou e a
        # pasta nova ainda nao existe, cai para o ultimo do ano anterior.
        for ano in sorted(por_ano, reverse=True):
            if por_ano[ano]:
                return [f"{PASTA_LIVE}/{ano}/{por_ano[ano][-1]}"]
        # Ano corrente vazio: tenta o anterior.
        anteriores = self._arquivos_do_ano(self.ate_ano - 1)
        if anteriores:
            return [f"{PASTA_LIVE}/{self.ate_ano - 1}/{anteriores[-1]}"]
        return []

    def collect(self) -> list[RawRecord]:
        registros: list[RawRecord] = []
        for caminho in self._caminhos_a_coletar():
            try:
                texto = self.client.get_text(URL_RAW.format(caminho=caminho))
            except Exception as exc:  # noqa: BLE001 - um arquivo nao derruba os outros
                self.falhas += 1
                logger.warning(
                    "download de um snapshot falhou",
                    extra={"caminho": caminho, "erro": f"{type(exc).__name__}: {exc}"},
                )
                continue

            nome = caminho.rsplit("/", 1)[-1]
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=ENDPOINT,
                    identificador=nome,
                    payload=texto,
                )
            )
        return registros

    def parse(self, registros: Sequence[RawRecord]) -> list[ResultadoRanking]:
        resultados: list[ResultadoRanking] = []
        for registro in registros:
            if registro.fonte != self.fonte or registro.endpoint != ENDPOINT:
                continue
            resultado = transformar(
                registro.payload, nome_arquivo=registro.identificador, regiao="global"
            )
            if resultado.linhas:
                resultados.append(resultado)
        return resultados

    def load(self, resultados: list[ResultadoRanking]) -> int:
        return sum(carregar(resultado) for resultado in resultados)

    def close(self) -> None:
        self.client.close()


def _ano_atual() -> int:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).year


def snapshots_no_banco(jogo: str = "counterstrike") -> list[str]:
    """As datas de referencia ja carregadas, em ISO - util para depurar."""
    from sqlalchemy import select

    from db.models import DimJogo, RankingExterno
    from db.session import session_scope

    with session_scope() as sessao:
        id_jogo = sessao.scalar(select(DimJogo.id_jogo).where(DimJogo.codigo == jogo))
        if id_jogo is None:
            return []
        datas = sessao.scalars(
            select(RankingExterno.data_referencia)
            .where(RankingExterno.id_jogo == id_jogo, RankingExterno.fonte == FONTE)
            .distinct()
            .order_by(RankingExterno.data_referencia)
        )
        return [d.isoformat() for d in datas]
