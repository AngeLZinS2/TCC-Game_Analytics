"""Coletor do indice de catalogo completo da Steam, com checkpoint (Fase 35).

Cobre o que faltava na integracao Steam ja existente: `SteamCollector` so
conhece o subconjunto "monitorado" (popularidade/semente); este coletor
paginao `IStoreService/GetAppList` (via `SteamStoreClient`) para o catalogo
INTEIRO, com o cursor (`last_appid`) persistido em `steam_sincronizacao` -
sobrevive a crash/restart, diferente do `todos_os_apps()` de
`steam_collector.py`, que mantem o cursor so em memoria.

Duas fases, na mesma tarefa:

  1. **catalogo_inicial** - enquanto nao concluida, cada execucao processa
     so `STEAM_SYNC_PAGES_PER_RUN` pagina(s) (ate 50.000 apps cada) e
     retorna - nunca o catalogo inteiro de uma vez, para nao segurar o
     laco do `agendador.py`.
  2. **catalogo_incremental** - depois de concluida, passa a rodar so
     quando `STEAM_SYNC_INTERVALO_HORAS` ja passou desde o ultimo sync,
     usando `if_modified_since`. Marca `pendente_atualizacao_preco` (em
     `load_steam_catalogo.py`) para qualquer app cujo `price_change_number`
     tenha mudado - a fila que `apps_com_preco_alterado()` depois drena.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import select

from config import Settings, get_settings
from models.models import SincronizacaoSteam
from models.session import session_scope
from services.collectors.base import BaseCollector, RawRecord
from services.collectors.steam_store_client import SteamStoreClient
from services.etl.load_steam_catalogo import carregar
from services.etl.transform_steam_catalogo import (
    FONTE,
    ResultadoCatalogoSteam,
    transformar,
)

FASE_INICIAL = "catalogo_inicial"
FASE_INCREMENTAL = "catalogo_incremental"


def _buscar_estado(sessao, tipo: str) -> SincronizacaoSteam | None:
    return sessao.scalar(
        select(SincronizacaoSteam).where(SincronizacaoSteam.tipo_sincronizacao == tipo)
    )


class SteamCatalogoCollector(BaseCollector[ResultadoCatalogoSteam]):
    fonte = FONTE

    def __init__(self, raw_storage: Any, settings: Settings | None = None) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.falhas = 0
        self.client = SteamStoreClient(self.settings)
        #: Setado em `collect()`, lido em `parse()` - mesmo padrao de estado
        #: entre os dois passos que `ItadCollector` ja usa.
        self._fase: str | None = None

    def _planejar(self) -> tuple[int, int | None]:
        """Decide a fase da execucao. Devolve `(last_appid, if_modified_since)`.

        `self._fase` fica `None` quando o sync incremental ainda nao venceu
        o intervalo configurado - a execucao inteira vira um no-op barato.
        """
        with session_scope() as sessao:
            estado_inicial = _buscar_estado(sessao, FASE_INICIAL)

            if estado_inicial is None or estado_inicial.status != "concluido":
                self._fase = FASE_INICIAL
                return (estado_inicial.last_appid or 0) if estado_inicial else 0, None

            estado_incremental = _buscar_estado(sessao, FASE_INCREMENTAL)
            referencia = (
                estado_incremental.concluida_em
                if estado_incremental and estado_incremental.concluida_em
                else estado_inicial.concluida_em
            )
            if referencia is not None:
                decorridas_h = (
                    datetime.now(timezone.utc) - referencia
                ).total_seconds() / 3600
                if decorridas_h < self.settings.steam_sync_intervalo_horas:
                    self._fase = None
                    return 0, None

            self._fase = FASE_INCREMENTAL
            base = referencia or (datetime.now(timezone.utc) - timedelta(days=1))
            return 0, int(base.timestamp())

    def collect(self) -> list[RawRecord]:
        last_appid, if_modified_since = self._planejar()
        if self._fase is None:
            return []

        registros: list[RawRecord] = []
        for pagina in range(self.settings.steam_sync_pages_per_run):
            try:
                resposta = self.client.listar_apps(
                    last_appid=last_appid, if_modified_since=if_modified_since
                )
            except Exception as exc:  # noqa: BLE001 - uma pagina ruim nao perde o checkpoint
                self.falhas += 1
                self.logger.warning(
                    "falha ao paginar GetAppList",
                    extra={
                        "fase": self._fase,
                        "pagina": pagina + 1,
                        "erro": f"{type(exc).__name__}: {exc}",
                    },
                )
                break

            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint="getapplist",
                    identificador=f"{self._fase}-{last_appid}",
                    payload=resposta,
                )
            )

            apps = resposta.get("apps") or []
            tem_mais = bool(resposta.get("have_more_results"))
            self.logger.info(
                "GetAppList pagina concluida",
                extra={
                    "fase": self._fase,
                    "pagina": pagina + 1,
                    "apps": len(apps),
                    "tem_mais": tem_mais,
                },
            )
            if not apps or not tem_mais:
                break

            last_appid = int(apps[-1]["appid"])
            ultima_pagina_do_orcamento = pagina + 1 >= self.settings.steam_sync_pages_per_run
            if not ultima_pagina_do_orcamento and self.settings.steam_sync_delay_seconds:
                time.sleep(self.settings.steam_sync_delay_seconds)

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoCatalogoSteam:
        return transformar(registros, self._fase)

    def load(self, dados: ResultadoCatalogoSteam) -> int:
        return carregar(dados)

    def close(self) -> None:
        self.client.close()
