"""Coletor do catalogo Xbox - a vitrine da aba "Xbox" do Catalogo de Jogos.

Duas fontes publicas (e NAO-oficiais) da Microsoft, fixadas no mercado BR:

1. `catalog.gamepass.com/sigls/v2` - a lista de `product_id`s que estao no Game
   Pass agora (uma "SIGL" por plano: console e PC).
2. `displaycatalog.mp.microsoft.com/v7.0/products` - a ficha de cada jogo (nome,
   arte, preco, faixa etaria), em lotes de ate ~20 ids por chamada.

Os alvos de cada rodada sao a UNIAO de: os ids do Game Pass, os `product_id` que
ja estao no banco (`dim_jogo_xbox`) e uma semente fixa - assim um jogo que entrou
pela vitrine continua sendo acompanhado mesmo depois de sair do Game Pass. A
coleta sob demanda passa `product_ids` explicito e coleta SO esses.

**Sem chave.** Os endpoints sao abertos; o que liga/desliga o coletor e o
`xbox_enabled` no agendador - mesmo contrato do HLTB e do OP.GG.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import select

from services.collectors.base import BaseCollector, RawRecord
from services.collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from models.models import DimJogoXbox
from models.session import session_scope
from services.etl.transform_xbox import (
    ENDPOINT_GAMEPASS,
    ENDPOINT_PRODUTOS,
    FONTE,
    ResultadoXbox,
    transformar,
)

logger = logging.getLogger(__name__)

#: Coleções do Game Pass, uma por plano. Os ids sao estaveis (mudam raramente);
#: se um dia mudarem, a lista aparece em `catalog.gamepass.com/sigls/v2`.
SIGL_CONSOLE = "f6f1f99f-9b49-4ccd-b3bf-4d9767a77f5e"
SIGL_PC = "fdd9e2a7-0fee-49f6-ad69-4354098401ff"

URL_SIGL = "https://catalog.gamepass.com/sigls/v2"
URL_PRODUTOS = "https://displaycatalog.mp.microsoft.com/v7.0/products"

#: Ids por chamada ao displaycatalog. A Microsoft aceita ate ~50, mas 20 mantem
#: a URL curta e a resposta manejavel.
LOTE = 20

ARQUIVO_SEMENTE = Path(__file__).resolve().parent / "seeds" / "xbox_apps.json"


def carregar_produtos_semente(caminho: Path = ARQUIVO_SEMENTE) -> list[str]:
    """Le a lista fixa de `product_id` monitorados (base vazia, primeiro `up`)."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return [str(item["product_id"]) for item in dados["produtos"]]


def produtos_monitorados() -> list[str]:
    """Os `product_id` que ja estao em `dim_jogo_xbox`.

    Mesma ideia do `_apps_monitorados` da Steam: o agendador acompanha o que ja
    foi trazido para o catalogo, em vez de uma lista decidida antes do uso.
    Devolve vazio quando a tabela esta vazia - ai a semente e a resposta certa.
    """
    with session_scope() as sessao:
        return list(sessao.scalars(select(DimJogoXbox.product_id)))


def _ids_da_sigl(payload: Any) -> list[str]:
    """A SIGL vem como lista: `[0]` e metadado (`siglId`), o resto tem `id`."""
    if not isinstance(payload, list):
        return []
    return [item["id"] for item in payload if isinstance(item, dict) and item.get("id")]


class XboxCollector(BaseCollector[ResultadoXbox]):
    fonte = FONTE

    def __init__(
        self,
        raw_storage: Any,
        settings: Settings | None = None,
        product_ids: Sequence[str] | None = None,
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        #: Setado -> coleta SO esses ids (coleta sob demanda). Nulo -> Game Pass
        #: + banco + semente.
        self.product_ids = list(product_ids) if product_ids else None
        self.falhas = 0

        self.client = RateLimitedClient(
            nome="xbox",
            intervalo_minimo=self.settings.xbox_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
        )

    def collect(self) -> list[RawRecord]:
        registros: list[RawRecord] = []
        ids_game_pass: set[str] = set()

        for sigl in (SIGL_CONSOLE, SIGL_PC):
            try:
                payload = self.client.get_json(
                    URL_SIGL,
                    {"id": sigl, "language": "pt-br", "market": self.settings.xbox_market},
                )
            except Exception as exc:  # noqa: BLE001 - uma SIGL nao derruba a outra
                self.falhas += 1
                logger.warning(
                    "SIGL do Game Pass falhou",
                    extra={"sigl": sigl, "erro": f"{type(exc).__name__}: {exc}"},
                )
                continue
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=ENDPOINT_GAMEPASS,
                    identificador=sigl,
                    payload=payload,
                )
            )
            ids_game_pass.update(_ids_da_sigl(payload))

        if self.product_ids is not None:
            alvos = sorted(set(self.product_ids))
        else:
            semente = set(ids_game_pass) or set(carregar_produtos_semente())
            alvos = sorted(
                ids_game_pass | set(produtos_monitorados()) | semente
            )

        logger.info(
            "alvos do catalogo Xbox",
            extra={"total": len(alvos), "no_game_pass": len(ids_game_pass)},
        )

        for i in range(0, len(alvos), LOTE):
            lote = alvos[i : i + LOTE]
            try:
                # Sem `fieldsTemplate=Details`: esse recorte omite `CMSVideos`
                # (os trailers em HLS). A resposta cheia so ~5% maior, e traz o
                # trailer + descricao longa junto.
                payload = self.client.get_json(
                    URL_PRODUTOS,
                    {
                        "bigIds": ",".join(lote),
                        "market": self.settings.xbox_market,
                        "languages": "pt-BR",
                    },
                )
            except Exception as exc:  # noqa: BLE001 - um lote nao derruba os outros
                self.falhas += 1
                logger.warning(
                    "lote do displaycatalog falhou",
                    extra={"lote": i // LOTE, "erro": f"{type(exc).__name__}: {exc}"},
                )
                continue
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=ENDPOINT_PRODUTOS,
                    identificador=f"lote-{i // LOTE}",
                    payload=payload,
                )
            )

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoXbox:
        return transformar(
            registros,
            moeda_mercado="BRL",
            janela_minutos=self.settings.snapshot_bucket_minutes,
        )

    def load(self, dados: ResultadoXbox) -> int:
        from services.etl.load_xbox import carregar

        return carregar(dados)

    def close(self) -> None:
        self.client.close()
