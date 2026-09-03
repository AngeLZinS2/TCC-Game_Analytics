"""Testes do ETL da Steam.

Os parsers sao a parte que quebra silenciosamente quando a API muda campos.
As fixtures sao payloads reais (reduzidos) e servem como contrato: se a Steam
mudar o schema, estes testes falham antes do dado sujo chegar no banco.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from collectors.base import RawRecord
from etl.transform_steam import (
    ENDPOINT_AVALIACOES,
    ENDPOINT_DETALHES,
    ENDPOINT_JOGADORES,
    parse_appdetails,
    parse_appreviews,
    parse_data_lancamento,
    parse_jogadores_simultaneos,
    parse_preco,
    transformar,
    truncar_janela,
)

MOMENTO = datetime(2026, 9, 2, 14, 37, 12, tzinfo=timezone.utc)


def _registro(endpoint: str, app_id: int, payload) -> RawRecord:
    return RawRecord(
        fonte="steam",
        endpoint=endpoint,
        identificador=str(app_id),
        payload=payload,
        coletado_em=MOMENTO,
    )


# --- appdetails ------------------------------------------------------------


def test_appdetails_jogo_gratuito(carregar_fixture):
    jogo = parse_appdetails(carregar_fixture("steam_appdetails_570"), 570)

    assert jogo is not None
    assert jogo.app_id == 570
    assert jogo.nome == "Dota 2"
    assert jogo.tipo == "game"
    assert jogo.desenvolvedora == "Valve"
    assert jogo.publicadora == "Valve"
    assert jogo.gratuito is True
    assert jogo.data_lancamento == date(2013, 7, 9)
    assert jogo.generos == ["Action", "Strategy", "Free To Play"]
    # Jogo gratuito nao traz price_overview: a dimensao fica sem preco.
    assert jogo.preco_atual is None
    assert jogo.nota_metacritic is None


def test_appdetails_jogo_pago_com_desconto(carregar_fixture):
    payload = carregar_fixture("steam_appdetails_1245620")
    jogo = parse_appdetails(payload, 1245620)

    assert jogo is not None
    assert jogo.nome == "ELDEN RING"
    # Centavos -> unidade monetaria.
    assert jogo.preco_atual == Decimal("124.95")
    assert jogo.moeda == "BRL"
    assert jogo.nota_metacritic == 94
    assert jogo.publicadora == "FromSoftware Inc., Bandai Namco Entertainment"
    assert jogo.data_lancamento == date(2022, 2, 24)


def test_appdetails_app_indisponivel_nao_quebra(carregar_fixture):
    payload = carregar_fixture("steam_appdetails_indisponivel")
    assert parse_appdetails(payload, 999999999) is None


def test_appdetails_data_nao_parseavel_preserva_texto(carregar_fixture):
    jogo = parse_appdetails(carregar_fixture("steam_appdetails_sem_data"), 3000001)

    assert jogo is not None
    assert jogo.data_lancamento is None
    assert jogo.data_lancamento_texto == "Q3 2026"
    assert jogo.publicadora is None
    assert jogo.generos == []


# --- preco (parte do fato) -------------------------------------------------


def test_preco_de_jogo_gratuito_vira_zero(carregar_fixture):
    preco = parse_preco(carregar_fixture("steam_appdetails_570"), 570)
    assert preco["preco_no_momento"] == Decimal("0.00")
    assert preco["desconto_percentual"] is None


def test_preco_com_desconto(carregar_fixture):
    preco = parse_preco(carregar_fixture("steam_appdetails_1245620"), 1245620)
    assert preco["preco_no_momento"] == Decimal("124.95")
    assert preco["moeda"] == "BRL"
    assert preco["desconto_percentual"] == 50


# --- appreviews ------------------------------------------------------------


def test_appreviews_calcula_percentual_positivo(carregar_fixture):
    resumo = parse_appreviews(carregar_fixture("steam_appreviews_570"))

    assert resumo["numero_avaliacoes"] == 2770557
    assert resumo["avaliacoes_positivas"] == 2231047
    assert resumo["classificacao_steam"] == "Very Positive"
    assert resumo["nota_avaliacoes"] == Decimal("80.53")


def test_appreviews_sem_avaliacoes_nao_divide_por_zero(carregar_fixture):
    resumo = parse_appreviews(carregar_fixture("steam_appreviews_sem_avaliacoes"))
    assert resumo["numero_avaliacoes"] == 0
    assert resumo["nota_avaliacoes"] is None


def test_appreviews_resposta_invalida():
    assert parse_appreviews({"success": 2}) == {}
    assert parse_appreviews(None) == {}


# --- jogadores simultaneos -------------------------------------------------


def test_jogadores_simultaneos(carregar_fixture):
    payload = carregar_fixture("steam_numberofcurrentplayers_570")
    assert parse_jogadores_simultaneos(payload) == 399114


def test_jogadores_simultaneos_resultado_invalido(carregar_fixture):
    payload = carregar_fixture("steam_numberofcurrentplayers_invalido")
    assert parse_jogadores_simultaneos(payload) is None


# --- helpers ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("9 Jul, 2013", date(2013, 7, 9)),
        ("24 Feb, 2022", date(2022, 2, 24)),
        ("Jul 9, 2013", date(2013, 7, 9)),
        ("2013", date(2013, 1, 1)),
        ("Coming soon", None),
        ("Q3 2026", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_data_lancamento(texto, esperado):
    assert parse_data_lancamento(texto) == esperado


def test_truncar_janela_alinha_a_hora():
    assert truncar_janela(MOMENTO, 60) == datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
    assert truncar_janela(MOMENTO, 15) == datetime(2026, 9, 2, 14, 30, tzinfo=timezone.utc)
    assert truncar_janela(MOMENTO, 1440) == datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)


def test_truncar_janela_rejeita_valor_invalido():
    with pytest.raises(ValueError):
        truncar_janela(MOMENTO, 0)


# --- montagem completa -----------------------------------------------------


def test_transformar_junta_tres_endpoints(carregar_fixture):
    registros = [
        _registro(ENDPOINT_DETALHES, 570, carregar_fixture("steam_appdetails_570")),
        _registro(ENDPOINT_AVALIACOES, 570, carregar_fixture("steam_appreviews_570")),
        _registro(
            ENDPOINT_JOGADORES,
            570,
            carregar_fixture("steam_numberofcurrentplayers_570"),
        ),
    ]

    resultado = transformar(registros, janela_minutos=60)

    assert len(resultado.jogos) == 1
    assert len(resultado.snapshots) == 1

    snapshot = resultado.snapshots[0]
    assert snapshot.app_id == 570
    assert snapshot.jogadores_simultaneos == 399114
    assert snapshot.numero_avaliacoes == 2770557
    assert snapshot.preco_no_momento == Decimal("0.00")
    assert snapshot.janela_coleta == datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
    assert snapshot.data_coleta == MOMENTO


def test_transformar_ignora_app_sem_dimensao(carregar_fixture):
    """Sem linha na dimensao o snapshot seria orfao (viola a FK)."""
    registros = [
        _registro(
            ENDPOINT_DETALHES, 999999999, carregar_fixture("steam_appdetails_indisponivel")
        ),
        _registro(
            ENDPOINT_JOGADORES,
            999999999,
            carregar_fixture("steam_numberofcurrentplayers_570"),
        ),
    ]

    resultado = transformar(registros)
    assert resultado.jogos == []
    assert resultado.snapshots == []


def test_transformar_ignora_outras_fontes(carregar_fixture):
    registro = RawRecord(
        fonte="opendota",
        endpoint="matches",
        identificador="123",
        payload={},
        coletado_em=MOMENTO,
    )
    assert transformar([registro]).total == 0
