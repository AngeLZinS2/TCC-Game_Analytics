"""Normalizacao dos payloads do IsThereAnyDeal (comparacao de preco).

Tres endpoints, tres formas de payload:

* `lookup`   - `{"found": bool, "game": {"id": "<uuid>", ...}}` - o id do jogo
  no ITAD a partir do Steam appid. Guardado por appid (`identificador`).
* `prices`   - `[{"id": "<uuid>", "deals": [{shop, price, regular, cut, url,
  drm}]}]` - o preco atual em cada loja.
* `historylow` - `[{"id": "<uuid>", "low": {shop, price, regular, cut,
  timestamp}}]` - o menor preco que o jogo ja teve.

O `prices` e o `historylow` vem por UUID do ITAD, nao por appid - por isso o
`transformar` reconstroi o mapa `uuid -> appid` a partir dos `lookup` antes de
casar. Funciona igual sobre payloads recem-coletados ou relidos do disco.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from pydantic import BaseModel, Field

from collectors.base import RawRecord

logger = logging.getLogger(__name__)

FONTE = "itad"
ENDPOINT_LOOKUP = "lookup"
ENDPOINT_PRECOS = "prices"
ENDPOINT_HISTORICO = "historylow"


class OfertaItad(BaseModel):
    loja_id: int
    loja: str
    preco: Decimal
    preco_normal: Decimal | None = None
    desconto: int | None = None
    moeda: str | None = None
    url: str | None = None
    drm: str | None = None


class MenorHistorico(BaseModel):
    loja: str | None = None
    preco: Decimal
    moeda: str | None = None
    data: date | None = None


class PrecoJogo(BaseModel):
    app_id: int
    itad_id: str
    ofertas: list[OfertaItad] = Field(default_factory=list)
    menor_historico: MenorHistorico | None = None


class ResultadoItad(BaseModel):
    #: appids que foram procurados e NAO existem no ITAD - viram `itad_id=""`
    #: em `dim_jogo_steam` para nao repetir a busca.
    sem_itad: list[int] = Field(default_factory=list)
    jogos: list[PrecoJogo] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.jogos)


def _dinheiro(bloco: Any) -> Decimal | None:
    if not isinstance(bloco, dict):
        return None
    valor = bloco.get("amount")
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except Exception:  # noqa: BLE001
        return None


def _moeda(bloco: Any) -> str | None:
    return bloco.get("currency") if isinstance(bloco, dict) else None


def parse_lookup(payload: Any) -> str | None:
    """`lookup` -> o UUID do jogo no ITAD, ou `None` se ele nao existe la."""
    if not isinstance(payload, dict) or not payload.get("found"):
        return None
    jogo = payload.get("game") or {}
    ident = jogo.get("id")
    return str(ident) if ident else None


def ofertas_de(deals: Any) -> list[OfertaItad]:
    """Publica de proposito: `collectors.itad_loja` reusa isto para a consulta
    ao vivo de UM jogo (o assistente perguntando por um jogo fora do banco),
    em vez de duplicar o parsing do payload `deals` do ITAD."""
    ofertas: list[OfertaItad] = []
    for deal in deals or []:
        if not isinstance(deal, dict):
            continue
        loja = deal.get("shop") or {}
        preco = _dinheiro(deal.get("price"))
        if preco is None or loja.get("id") is None:
            continue
        drm = deal.get("drm") or []
        ofertas.append(
            OfertaItad(
                loja_id=int(loja["id"]),
                loja=str(loja.get("name") or f"loja {loja['id']}"),
                preco=preco,
                preco_normal=_dinheiro(deal.get("regular")),
                desconto=deal.get("cut"),
                moeda=_moeda(deal.get("price")),
                url=deal.get("url") or None,
                drm=", ".join(d["name"] for d in drm if isinstance(d, dict) and d.get("name"))
                or None,
            )
        )
    return ofertas


def historico_de(low: Any) -> MenorHistorico | None:
    if not isinstance(low, dict):
        return None
    preco = _dinheiro(low.get("price"))
    if preco is None:
        return None
    carimbo = low.get("timestamp")
    quando: date | None = None
    if isinstance(carimbo, str):
        try:
            quando = datetime.fromisoformat(carimbo.replace("Z", "+00:00")).date()
        except ValueError:
            quando = None
    return MenorHistorico(
        loja=(low.get("shop") or {}).get("name"),
        preco=preco,
        moeda=_moeda(low.get("price")),
        data=quando,
    )


def _por_id(payload: Any) -> dict[str, dict]:
    """`[{"id": uuid, ...}]` -> `{uuid: item}`. Aceita lista ou `{"data": [...]}`."""
    lista = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(lista, list):
        return {}
    return {str(item["id"]): item for item in lista if isinstance(item, dict) and item.get("id")}


def transformar(registros: Iterable[RawRecord]) -> ResultadoItad:
    """Junta lookup + prices + historylow numa lista de `PrecoJogo`."""
    lookups: list[RawRecord] = []
    precos: list[RawRecord] = []
    historicos: list[RawRecord] = []
    for registro in registros:
        if registro.fonte != FONTE:
            continue
        {
            ENDPOINT_LOOKUP: lookups,
            ENDPOINT_PRECOS: precos,
            ENDPOINT_HISTORICO: historicos,
        }.get(registro.endpoint, []).append(registro)

    resultado = ResultadoItad()

    # appid <-> uuid, a partir dos lookups
    uuid_por_app: dict[int, str] = {}
    for registro in lookups:
        try:
            app_id = int(registro.identificador)
        except ValueError:
            continue
        uuid = parse_lookup(registro.payload)
        if uuid:
            uuid_por_app[app_id] = uuid
        else:
            resultado.sem_itad.append(app_id)

    app_por_uuid = {uuid: app for app, uuid in uuid_por_app.items()}
    if not app_por_uuid:
        return resultado

    ofertas_por_uuid: dict[str, dict] = {}
    for registro in precos:
        ofertas_por_uuid.update(_por_id(registro.payload))

    historico_por_uuid: dict[str, dict] = {}
    for registro in historicos:
        historico_por_uuid.update(_por_id(registro.payload))

    for uuid, app_id in app_por_uuid.items():
        item = ofertas_por_uuid.get(uuid) or {}
        low = historico_por_uuid.get(uuid) or {}
        resultado.jogos.append(
            PrecoJogo(
                app_id=app_id,
                itad_id=uuid,
                ofertas=ofertas_de(item.get("deals")),
                menor_historico=historico_de(low.get("low")),
            )
        )

    return resultado
