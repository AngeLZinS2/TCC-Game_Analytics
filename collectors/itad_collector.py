"""Coletor de preco via IsThereAnyDeal - "esta mais barato fora da Steam?".

O ITAD agrega o preco atual de ~33 lojas (Nuuvem, GOG, Fanatical, Humble...)
por Steam appid. O fluxo, por rodada:

1. `lookup` (GET, um por appid) - so para os jogos pagos que ainda nao tem o
   UUID do ITAD cacheado em `dim_jogo_steam.itad_id`. O resultado e cacheado;
   `""` marca "ja procurei, nao existe la".
2. `prices` (POST, um so) - a lista inteira de UUIDs no corpo.
3. `historylow` (POST, um so) - idem, para o menor preco de sempre.

Sao 2 chamadas fixas + N lookups so na primeira vez que cada jogo aparece.
O limite do ITAD e 1000 req / 5 min; o intervalo padrao (0,4s) da folga
enorme.

**Sem `ITAD_API_KEY` o coletor recusa rodar** - e o painel "Onde comprar" nao
aparece. Estado esperado, como o assistente sem OpenRouter.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import or_, select

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from db.models import DimJogoSteam
from db.session import session_scope
from etl.load_itad import carregar
from etl.transform_itad import (
    ENDPOINT_HISTORICO,
    ENDPOINT_LOOKUP,
    ENDPOINT_PRECOS,
    FONTE,
    ResultadoItad,
    transformar,
)

logger = logging.getLogger(__name__)

#: Quantas ofertas o ITAD devolve por jogo. 8 cobre as lojas relevantes sem
#: encher a resposta de mercado paralelo obscuro.
OFERTAS_POR_JOGO = 8


class SemChaveItadError(RuntimeError):
    """`ITAD_API_KEY` nao configurada - o coletor nao tem o que fazer."""


def jogos_para_preco(limite: int | None = None) -> list[tuple[int, str | None]]:
    """`(app_id, itad_id)` dos jogos que valem consultar preco.

    Jogo gratuito nao entra (nao ha o que comparar). Jogo com `itad_id = ""`
    ja foi procurado e nao existe no ITAD - fica de fora ate alguem forcar.
    """
    with session_scope() as sessao:
        consulta = (
            select(DimJogoSteam.app_id, DimJogoSteam.itad_id)
            .where(
                or_(DimJogoSteam.gratuito.is_(None), DimJogoSteam.gratuito.is_(False)),
                or_(DimJogoSteam.itad_id.is_(None), DimJogoSteam.itad_id != ""),
            )
            .order_by(DimJogoSteam.app_id)
        )
        if limite:
            consulta = consulta.limit(limite)
        return [(linha.app_id, linha.itad_id) for linha in sessao.execute(consulta)]


class ItadCollector(BaseCollector[ResultadoItad]):
    fonte = FONTE

    def __init__(
        self,
        raw_storage: Any,
        settings: Settings | None = None,
        limite: int | None = None,
        forcar_lookup: bool = False,
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.limite = limite
        self.forcar_lookup = forcar_lookup
        self.falhas = 0

        self.client = RateLimitedClient(
            nome="itad",
            intervalo_minimo=self.settings.itad_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
        )

    @property
    def _base(self) -> str:
        return self.settings.itad_base_url.rstrip("/")

    def _params(self, **extra: Any) -> dict[str, Any]:
        return {"key": self.settings.itad_api_key, **extra}

    def collect(self) -> list[RawRecord]:
        if not self.settings.itad_api_key:
            raise SemChaveItadError(
                "ITAD_API_KEY nao configurada. Pegue a chave gratuita em "
                "https://isthereanydeal.com/apps/my/ e coloque no .env."
            )

        alvos = jogos_para_preco(self.limite)
        if not alvos:
            logger.info("nenhum jogo pago para consultar preco")
            return []

        registros: list[RawRecord] = []
        uuids: dict[str, int] = {}  # uuid -> app_id

        for app_id, itad_id in alvos:
            if itad_id and not self.forcar_lookup:
                uuids[itad_id] = app_id
                continue
            try:
                payload = self.client.get_json(
                    f"{self._base}/games/lookup/v1", self._params(appid=app_id)
                )
            except Exception as exc:  # noqa: BLE001 - um jogo nao derruba os outros
                self.falhas += 1
                logger.warning(
                    "lookup de um jogo falhou",
                    extra={"app_id": app_id, "erro": f"{type(exc).__name__}: {exc}"},
                )
                continue
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=ENDPOINT_LOOKUP,
                    identificador=str(app_id),
                    payload=payload,
                )
            )
            uuid = (payload.get("game") or {}).get("id") if payload.get("found") else None
            if uuid:
                uuids[str(uuid)] = app_id

        if not uuids:
            return registros

        lista = list(uuids)
        for endpoint, caminho in (
            (ENDPOINT_PRECOS, "/games/prices/v3"),
            (ENDPOINT_HISTORICO, "/games/historylow/v1"),
        ):
            try:
                params = self._params(country=self.settings.itad_country)
                if endpoint == ENDPOINT_PRECOS:
                    params["capacity"] = OFERTAS_POR_JOGO
                payload = self.client.post_json(
                    f"{self._base}{caminho}", json=lista, params=params
                )
            except Exception as exc:  # noqa: BLE001
                self.falhas += 1
                logger.warning(
                    "chamada em lote do ITAD falhou",
                    extra={"endpoint": endpoint, "erro": f"{type(exc).__name__}: {exc}"},
                )
                continue
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=endpoint,
                    identificador=f"lote-{len(lista)}",
                    payload=payload,
                )
            )

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoItad:
        return transformar(registros)

    def load(self, resultado: ResultadoItad) -> int:
        return carregar(resultado)

    def close(self) -> None:
        self.client.close()
