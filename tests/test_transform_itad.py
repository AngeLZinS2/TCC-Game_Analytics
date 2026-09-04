"""Testes do parser do IsThereAnyDeal.

Sem rede e sem banco: `transformar` sobre RawRecord's montados a partir das
fixtures (payloads no formato documentado, reduzidos). O que se protege e o
casamento uuid<->appid e a extracao de preco/desconto/menor historico.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from collectors.base import RawRecord
from etl.transform_itad import (
    ENDPOINT_HISTORICO,
    ENDPOINT_LOOKUP,
    ENDPOINT_PRECOS,
    parse_lookup,
    transformar,
)

UUID = "018d937f-5a2b-72c1-9e00-abc123456789"
APP = 1245620


def _reg(endpoint: str, ident: str, payload) -> RawRecord:
    return RawRecord(fonte="itad", endpoint=endpoint, identificador=ident, payload=payload)


def test_parse_lookup(carregar_fixture):
    assert parse_lookup(carregar_fixture("itad_lookup")) == UUID
    assert parse_lookup(carregar_fixture("itad_lookup_nao_encontrado")) is None
    assert parse_lookup({}) is None


def test_transformar_junta_lookup_precos_e_historico(carregar_fixture):
    registros = [
        _reg(ENDPOINT_LOOKUP, str(APP), carregar_fixture("itad_lookup")),
        _reg(ENDPOINT_PRECOS, "lote-1", carregar_fixture("itad_prices")),
        _reg(ENDPOINT_HISTORICO, "lote-1", carregar_fixture("itad_historylow")),
    ]
    resultado = transformar(registros)

    assert resultado.total == 1
    jogo = resultado.jogos[0]
    assert jogo.app_id == APP
    assert jogo.itad_id == UUID

    # ofertas na ordem em que vieram (o loader/ API ordenam por preco depois)
    lojas = {o.loja: o for o in jogo.ofertas}
    assert set(lojas) == {"Steam", "Nuuvem", "Fanatical"}
    assert lojas["Nuuvem"].preco == Decimal("149.99")
    assert lojas["Nuuvem"].preco_normal == Decimal("249.9")
    assert lojas["Nuuvem"].desconto == 40
    assert lojas["Nuuvem"].moeda == "BRL"
    assert lojas["Nuuvem"].drm == "Steam"

    assert jogo.menor_historico.preco == Decimal("99.9")
    assert jogo.menor_historico.loja == "Nuuvem"
    assert jogo.menor_historico.data == date(2025, 11, 28)


def test_transformar_marca_appid_sem_itad(carregar_fixture):
    registros = [
        _reg(ENDPOINT_LOOKUP, "999999", carregar_fixture("itad_lookup_nao_encontrado")),
    ]
    resultado = transformar(registros)
    assert resultado.sem_itad == [999999]
    assert resultado.jogos == []


def test_transformar_sem_lookup_nao_casa_nada(carregar_fixture):
    """Sem o lookup nao ha como ligar o UUID do `prices` a um appid nosso."""
    registros = [_reg(ENDPOINT_PRECOS, "lote-1", carregar_fixture("itad_prices"))]
    assert transformar(registros).total == 0


def test_transformar_jogo_sem_oferta_ainda_entra(carregar_fixture):
    """Lookup achou o jogo, mas o `prices` nao trouxe deal nenhum (jogo sem
    venda no momento) - a linha entra mesmo assim, com ofertas vazias, para o
    `itad_id` ser cacheado."""
    registros = [
        _reg(ENDPOINT_LOOKUP, str(APP), carregar_fixture("itad_lookup")),
        _reg(ENDPOINT_PRECOS, "lote-1", [{"id": UUID, "deals": []}]),
    ]
    resultado = transformar(registros)
    assert resultado.total == 1
    assert resultado.jogos[0].ofertas == []
    assert resultado.jogos[0].itad_id == UUID


def test_transformar_ignora_outras_fontes(carregar_fixture):
    reg = RawRecord(fonte="steam", endpoint="appdetails", identificador="1", payload={})
    assert transformar([reg]).total == 0
