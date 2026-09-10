"""Testes do ETL do catalogo Xbox.

Os endpoints da Microsoft nao sao documentados: as fixtures sao payloads reais
(reduzidos) + dois produtos sinteticos (promo e gratuito) e servem de contrato.
Se a Microsoft mudar o schema, estes testes falham antes do dado sujo chegar no
banco.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from services.collectors.base import RawRecord
from services.etl.transform_xbox import (
    ENDPOINT_GAMEPASS,
    ENDPOINT_PRODUTOS,
    FONTE,
    transformar,
    truncar_janela,
)

MOMENTO = datetime(2026, 9, 9, 14, 37, 12, tzinfo=timezone.utc)


def _sigl(nome: str, payload) -> RawRecord:
    return RawRecord(
        fonte=FONTE, endpoint=ENDPOINT_GAMEPASS, identificador=nome,
        payload=payload, coletado_em=MOMENTO,
    )


def _produtos(payload) -> RawRecord:
    return RawRecord(
        fonte=FONTE, endpoint=ENDPOINT_PRODUTOS, identificador="lote-0",
        payload=payload, coletado_em=MOMENTO,
    )


def _registros(carregar_fixture):
    return [
        _sigl("console", carregar_fixture("xbox_gamepass_console")),
        _sigl("pc", carregar_fixture("xbox_gamepass_pc")),
        _produtos(carregar_fixture("xbox_displaycatalog_lote")),
    ]


def test_transformar_junta_game_pass_e_ficha(carregar_fixture):
    resultado = transformar(_registros(carregar_fixture), janela_minutos=360)

    assert resultado.total == 4
    assert len(resultado.snapshots) == 4
    por_id = {j.product_id: j for j in resultado.jogos}
    assert set(por_id) == {
        "9NPDN9R45JX4", "9P8LR42PTRGJ", "9DISCOUNT0001", "9FREEGAME0001"
    }


def test_jogo_real_pago_sem_desconto(carregar_fixture):
    jogo = {
        j.product_id: j
        for j in transformar(_registros(carregar_fixture)).jogos
    }["9NPDN9R45JX4"]

    assert jogo.nome == "1000xRESIST"
    assert jogo.desenvolvedora == "sunset visitor 斜陽過客"
    assert jogo.publicadora == "Fellow Traveller"
    assert jogo.preco_atual == Decimal("97.95")
    assert jogo.preco_normal == Decimal("97.95")
    assert jogo.desconto_percentual is None
    assert jogo.moeda == "BRL"
    assert jogo.gratuito is None
    assert jogo.no_game_pass is True  # esta na SIGL do console
    assert jogo.data_lancamento == date(2025, 11, 4)
    assert jogo.faixa_etaria == 16
    assert jogo.generos == ["Ação e aventura"]
    assert jogo.imagem_header and jogo.imagem_header.startswith("https://")
    assert jogo.imagem_capa and jogo.imagem_capa.startswith("https://")
    assert jogo.url_loja.endswith("9NPDN9R45JX4")


def test_jogo_em_promocao_calcula_desconto(carregar_fixture):
    jogo = {
        j.product_id: j
        for j in transformar(_registros(carregar_fixture)).jogos
    }["9DISCOUNT0001"]

    assert jogo.preco_atual == Decimal("49.99")
    assert jogo.preco_normal == Decimal("99.99")
    assert jogo.desconto_percentual == 50
    assert jogo.no_game_pass is False  # sintetico, fora da SIGL
    assert jogo.generos == ["RPG", "Estratégia"]


def test_jogo_gratuito(carregar_fixture):
    jogo = {
        j.product_id: j
        for j in transformar(_registros(carregar_fixture)).jogos
    }["9FREEGAME0001"]

    assert jogo.gratuito is True
    assert jogo.preco_atual is None
    assert jogo.moeda is None
    assert jogo.desconto_percentual is None


def test_nota_recursos_conquistas_e_classificacao(carregar_fixture):
    jogo = {
        j.product_id: j
        for j in transformar(_registros(carregar_fixture)).jogos
    }["9NPDN9R45JX4"]

    # nota da Store (UsageData) - AllTime e a oficial, 7Days a recente
    assert jogo.nota == Decimal("3.8")
    assert jogo.numero_avaliacoes == 1473
    assert jogo.nota_recente == Decimal("3.7")

    # recursos traduzidos, sem o ruido de infra (XboxLive/XPA/BroadcastSupport)
    assert "4K" in jogo.recursos
    assert "Um jogador" in jogo.recursos
    assert "Otimizado p/ Series X|S" in jogo.recursos
    assert "XboxLive" not in jogo.recursos and "XPA" not in jogo.recursos

    assert jogo.tem_conquistas is True

    # classificacao pega a DJCTQ (Brasil) mesmo com 11 sistemas na lista
    assert jogo.classificacao_etaria == "14"
    assert "Violência" in jogo.descritores_conteudo
    assert "Drogas lícitas" in jogo.descritores_conteudo

    assert jogo.descricao and len(jogo.descricao) > 10

    # midias no formato do CarrosselMidia (tipo/url/cartaz/titulo): trailer
    # (CMSVideos -> HLS) primeiro, capturas depois; sem url repetida
    assert jogo.midias[0]["tipo"] == "video"
    assert jogo.midias[0]["url"].endswith(".m3u8?packagedStreaming=true")
    assert jogo.midias[0]["cartaz"].startswith("https://")
    assert jogo.midias[0]["titulo"]
    assert [m["tipo"] for m in jogo.midias[1:]] == ["imagem", "imagem"]
    assert all({"tipo", "url", "cartaz", "titulo"} <= m.keys() for m in jogo.midias)
    assert len({m["url"] for m in jogo.midias}) == len(jogo.midias)


def test_sem_avaliacao_nao_inventa_nota(carregar_fixture):
    jogo = {
        j.product_id: j
        for j in transformar(_registros(carregar_fixture)).jogos
    }["9FREEGAME0001"]

    assert jogo.nota is None
    assert jogo.numero_avaliacoes is None
    assert jogo.nota_recente is None
    assert jogo.tem_conquistas is False
    assert "Multi-jogador online" in jogo.recursos
    assert jogo.classificacao_etaria is None
    assert jogo.descritores_conteudo == []
    assert jogo.midias == []


def test_snapshot_carrega_a_nota(carregar_fixture):
    resultado = transformar(_registros(carregar_fixture), janela_minutos=360)
    snap = {s.product_id: s for s in resultado.snapshots}["9P8LR42PTRGJ"]
    assert snap.nota == Decimal("3.9")
    assert snap.numero_avaliacoes == 2900
    assert snap.nota_recente == Decimal("2.9")


def test_snapshot_usa_janela_truncada(carregar_fixture):
    resultado = transformar(_registros(carregar_fixture), janela_minutos=360)
    janelas = {s.janela_coleta for s in resultado.snapshots}
    assert len(janelas) == 1
    janela = next(iter(janelas))
    assert janela == truncar_janela(janela, 360)
    assert janela.minute == 0 and janela.second == 0


def test_ignora_registros_de_outras_fontes(carregar_fixture):
    outro = RawRecord(
        fonte="steam", endpoint="appdetails", identificador="570",
        payload={"Products": [{"ProductId": "X", "LocalizedProperties": [{"ProductTitle": "X"}]}]},
        coletado_em=MOMENTO,
    )
    resultado = transformar([outro], janela_minutos=360)
    assert resultado.total == 0


def test_produto_sem_id_ou_nome_e_descartado(carregar_fixture):
    payload = {"Products": [
        {"LocalizedProperties": [{"ProductTitle": "sem id"}]},
        {"ProductId": "9SEMNOME0001", "LocalizedProperties": [{}]},
        {"ProductId": "9OK00000001", "LocalizedProperties": [{"ProductTitle": "ok"}],
         "DisplaySkuAvailabilities": [], "MarketProperties": [], "Properties": {}},
    ]}
    resultado = transformar([_produtos(payload)], janela_minutos=360)
    assert [j.product_id for j in resultado.jogos] == ["9OK00000001"]


def test_sem_game_pass_marca_no_game_pass_false(carregar_fixture):
    """Sem nenhuma SIGL, todo jogo fica `no_game_pass=False`."""
    resultado = transformar(
        [_produtos(carregar_fixture("xbox_displaycatalog_lote"))], janela_minutos=360
    )
    assert all(j.no_game_pass is False for j in resultado.jogos)
