"""Coletor de preco via IsThereAnyDeal - "esta mais barato fora da Steam?".

O ITAD agrega o preco atual de ~33 lojas (Nuuvem, GOG, Fanatical, Humble...)
por Steam appid. O fluxo, por rodada:

1. `lookup` (GET, um por appid) - so para os jogos pagos que ainda nao tem o
   UUID do ITAD cacheado em `dim_jogo_steam.itad_id`. O resultado e cacheado;
   `""` marca "ja procurei, nao existe la". Para os jogos que JA tem UUID o
   `parse` sintetiza um `lookup` em memoria (nunca gravado) com o valor
   cacheado - e o que deixa o `transformar` reconstruir o mapa `uuid -> appid`
   sem uma ida a rede. Sem isso o lote so atualizava jogo novo.
2. `prices` (POST) - a lista de UUIDs no corpo, em lotes de ate `LOTE_MAX`.
3. `historylow` (POST) - idem, para o menor preco de sempre.

Sao ~2 chamadas por lote de 200 jogos + N lookups so na primeira vez que cada
jogo aparece. O limite do ITAD e 1000 req / 5 min; o intervalo padrao (0,4s)
da folga enorme.

**Sem `ITAD_API_KEY` o coletor recusa rodar** - e o painel "Onde comprar" nao
aparece. Estado esperado, como o assistente sem OpenRouter.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import and_, or_, select

from services.collectors.base import BaseCollector, RawRecord
from services.collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from models.models import DimJogoSteam
from models.session import session_scope
from services.etl.load_itad import carregar
from services.etl.transform_itad import (
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

#: Teto de ids por chamada em `prices/v3` e `historylow/v1` (doc do ITAD:
#: "[ 1 .. 200 ] items"). Acima disso a API corta a lista em silencio e os
#: jogos do fim do lote nunca atualizam. Coletamos em lotes desse tamanho.
LOTE_MAX = 200


class SemChaveItadError(RuntimeError):
    """`ITAD_API_KEY` nao configurada - o coletor nao tem o que fazer."""


def jogos_para_preco(
    limite: int | None = None,
    app_ids: Sequence[int] | None = None,
    revalidar_vazios_dias: int | None = None,
) -> list[tuple[int, str | None]]:
    """`(app_id, itad_id)` dos jogos que valem consultar preco.

    Jogo gratuito nao entra (nao ha o que comparar). Jogo com `itad_id = ""`
    ja foi procurado e nao existe no ITAD - fica de fora ate alguem forcar.

    `revalidar_vazios_dias`: se dado, jogo com `itad_id = ""` cuja ultima
    tentativa (`coletado_preco_em`) passou desse tempo volta pra fila - um
    pre-venda que ainda nao estava no ITAD entra quando lanca. O `""` e falsy,
    entao o coletor refaz o `lookup` dele sozinho.

    `app_ids` restringe a esses apps - e o caminho da coleta sob demanda,
    quando alguem acabou de buscar um jogo e quer o preco na hora.
    """
    nao_gratuito = or_(
        DimJogoSteam.gratuito.is_(None), DimJogoSteam.gratuito.is_(False)
    )
    tem_itad = or_(DimJogoSteam.itad_id.is_(None), DimJogoSteam.itad_id != "")
    if revalidar_vazios_dias is not None:
        corte = datetime.now(timezone.utc) - timedelta(days=revalidar_vazios_dias)
        tem_itad = or_(
            tem_itad,
            and_(
                DimJogoSteam.itad_id == "",
                or_(
                    DimJogoSteam.coletado_preco_em.is_(None),
                    DimJogoSteam.coletado_preco_em < corte,
                ),
            ),
        )
    with session_scope() as sessao:
        consulta = (
            select(DimJogoSteam.app_id, DimJogoSteam.itad_id)
            .where(nao_gratuito, tem_itad)
            .order_by(DimJogoSteam.app_id)
        )
        if app_ids is not None:
            consulta = consulta.where(DimJogoSteam.app_id.in_(list(app_ids)))
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
        app_ids: Sequence[int] | None = None,
        revalidar_vazios_dias: int | None = None,
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.limite = limite
        self.forcar_lookup = forcar_lookup
        #: Quando setado, coleta so esses apps (coleta sob demanda da busca).
        self.app_ids = list(app_ids) if app_ids is not None else None
        #: Jogo `itad_id=""` (nao achado antes) mais velho que isso volta pra
        #: fila de lookup - pre-venda que so entrou no ITAD depois.
        self.revalidar_vazios_dias = revalidar_vazios_dias
        #: `app_id -> uuid` dos jogos ja conhecidos (sem `lookup` nesta rodada).
        #: O `parse` sintetiza um `lookup` em memoria pra cada um - e o que
        #: liga o UUID de volta ao appid sem pagar uma ida a rede.
        self._uuids_cacheados: dict[int, str] = {}
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

        alvos = jogos_para_preco(
            self.limite, self.app_ids, self.revalidar_vazios_dias
        )
        if not alvos:
            logger.info(
                "nenhum jogo pago para consultar preco",
                extra={"app_ids": self.app_ids},
            )
            return []

        registros: list[RawRecord] = []
        uuids: dict[str, int] = {}  # uuid -> app_id
        self._uuids_cacheados: dict[int, str] = {}  # app_id -> uuid, sem lookup

        for app_id, itad_id in alvos:
            if itad_id and not self.forcar_lookup:
                uuids[itad_id] = app_id
                self._uuids_cacheados[app_id] = itad_id
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
        lotes = [lista[i : i + LOTE_MAX] for i in range(0, len(lista), LOTE_MAX)]
        for endpoint, caminho in (
            (ENDPOINT_PRECOS, "/games/prices/v3"),
            (ENDPOINT_HISTORICO, "/games/historylow/v1"),
        ):
            for numero, lote in enumerate(lotes, start=1):
                try:
                    params = self._params(country=self.settings.itad_country)
                    if endpoint == ENDPOINT_PRECOS:
                        params["capacity"] = OFERTAS_POR_JOGO
                    payload = self.client.post_json(
                        f"{self._base}{caminho}", json=lote, params=params
                    )
                except Exception as exc:  # noqa: BLE001
                    self.falhas += 1
                    logger.warning(
                        "chamada em lote do ITAD falhou",
                        extra={
                            "endpoint": endpoint,
                            "lote": f"{numero}/{len(lotes)}",
                            "erro": f"{type(exc).__name__}: {exc}",
                        },
                    )
                    continue
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint=endpoint,
                        identificador=f"lote-{numero}-{len(lote)}",
                        payload=payload,
                    )
                )

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoItad:
        # `lookup` sinteticos (so em memoria, nunca gravados) pros jogos ja
        # conhecidos: o `transformar` monta o mapa uuid->appid a partir dos
        # registros `lookup`, e um jogo cacheado nao gera nenhum. Sem isto o
        # lote so atualizava jogo novo.
        ja_tem = {
            r.identificador for r in registros if r.endpoint == ENDPOINT_LOOKUP
        }
        sinteticos = [
            RawRecord(
                fonte=self.fonte,
                endpoint=ENDPOINT_LOOKUP,
                identificador=str(app_id),
                payload={"found": True, "game": {"id": uuid}, "_cache": True},
            )
            for app_id, uuid in self._uuids_cacheados.items()
            if str(app_id) not in ja_tem
        ]
        return transformar([*registros, *sinteticos])

    def load(self, resultado: ResultadoItad) -> int:
        return carregar(resultado)

    def close(self) -> None:
        self.client.close()
