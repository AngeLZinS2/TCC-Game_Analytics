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
    ENDPOINT_NOTICIAS,
    ENDPOINT_STEAMSPY,
    _parse_idiomas,
    _parse_midias,
    _texto_de_html,
    parse_appdetails,
    parse_appreviews,
    parse_data_lancamento,
    parse_jogadores_simultaneos,
    parse_noticias,
    parse_preco,
    parse_steamspy,
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


# --- ficha do jogo (Fase 16) ---------------------------------------------


def test_appdetails_ficha_extrai_recursos_e_plataformas(carregar_fixture):
    jogo = parse_appdetails(carregar_fixture("steam_appdetails_ficha"), 3751260)
    assert "Steam Achievements" in jogo.recursos
    assert jogo.plataformas == ["windows"]
    assert jogo.suporte_controle == "full"
    assert jogo.conquistas_total == 46
    assert jogo.analises_totais == 3767
    assert jogo.dlc_ids == [4417550]
    assert jogo.em_breve is False
    assert jogo.site_oficial == "https://dawnwalkergame.com"


def test_appdetails_ficha_traduz_descritores_e_classificacoes(carregar_fixture):
    jogo = parse_appdetails(carregar_fixture("steam_appdetails_ficha"), 3751260)
    assert jogo.faixa_etaria == 18
    # IDs 1,2,5 -> textos em portugues
    assert any("sexual" in d.lower() for d in jogo.descritores_conteudo)
    assert jogo.classificacoes.get("pegi") == "18"
    assert "esrb" in jogo.classificacoes


def test_appdetails_ficha_idiomas_com_e_sem_audio(carregar_fixture):
    jogo = parse_appdetails(carregar_fixture("steam_appdetails_ficha"), 3751260)
    assert "English" in jogo.idiomas
    assert "English" in jogo.idiomas_com_audio
    # todo idioma dublado tambem esta na lista geral
    assert set(jogo.idiomas_com_audio) <= set(jogo.idiomas)


def test_parse_idiomas_marca_audio_pelo_asterisco():
    todos, audio = _parse_idiomas(
        "English<strong>*</strong>, Portuguese - Brazil<br><strong>*</strong>full audio"
    )
    assert todos == ["English", "Portuguese - Brazil"]
    assert audio == ["English"]


def test_texto_de_html_tira_marcacao_e_corta():
    assert _texto_de_html("<p>Olá <b>mundo</b></p>") == "Olá mundo"
    assert _texto_de_html("", limite=10) is None
    cortado = _texto_de_html("<p>" + "palavra " * 50 + "</p>", limite=30)
    assert cortado.endswith("…") and len(cortado) <= 32


def test_texto_de_html_limpa_o_corpo_bbcode_de_uma_noticia():
    """O feed de noticias vem em BBCode com imagem, token da Steam e lista -
    nada disso pode sobrar no resumo que a tela mostra."""
    bruto = (
        'Hotfix em andamento! [img src="{STEAM_CLAN_IMAGE}/1/a.png"] '
        "Mudancas: [list][*][p]Corrigido um crash[/p][/*][/list]"
        "[url=https://ex.com]Notas completas[/url]"
    )
    limpo = _texto_de_html(bruto, limite=300)
    assert "[" not in limpo and "{" not in limpo and "img" not in limpo
    assert "Corrigido um crash" in limpo and "Notas completas" in limpo


def test_parse_steamspy_traz_donos_e_tags(carregar_fixture):
    dados = parse_steamspy(carregar_fixture("steam_steamspy_570"))
    assert ".." in dados["donos_estimados"]  # faixa, nunca numero exato
    assert isinstance(dados["tags_comunidade"], dict)
    assert all(v > 0 for v in dados["tags_comunidade"].values())


def test_parse_steamspy_jogo_novo_sem_dado_volta_vazio():
    assert parse_steamspy({"appid": 999, "owners": "0 .. 0", "tags": [], "average_forever": 0}) == {}
    assert parse_steamspy({}) == {}


def test_parse_steamspy_faixa_baixa_ainda_e_dado():
    # "0 .. 20,000" e o balde mais baixo do SteamSpy, mas e informacao real
    # ("menos de 20 mil donos") - diferente de nao ter estimativa nenhuma.
    dados = parse_steamspy({"appid": 999, "owners": "0 .. 20,000", "tags": []})
    assert dados["donos_estimados"] == "0 .. 20,000"


def test_parse_noticias(carregar_fixture):
    noticias = parse_noticias(carregar_fixture("steam_news_570"), 570)
    assert len(noticias) == 3
    n = noticias[0]
    assert n.gid and n.titulo and n.app_id == 570
    assert n.publicado_em is not None
    # o resumo nao tem HTML cru
    assert n.resumo is None or "<" not in n.resumo


def test_parse_noticias_payload_ruim_nao_levanta():
    assert parse_noticias({}, 570) == []
    assert parse_noticias({"appnews": {"newsitems": [{"gid": "1"}]}}, 570) == []  # sem titulo


def test_transformar_funde_steamspy_e_noticias_no_jogo(carregar_fixture):
    registros = [
        _registro(ENDPOINT_DETALHES, 570, carregar_fixture("steam_appdetails_570")),
        _registro(ENDPOINT_STEAMSPY, 570, carregar_fixture("steam_steamspy_570")),
        _registro(ENDPOINT_NOTICIAS, 570, carregar_fixture("steam_news_570")),
    ]
    resultado = transformar(registros)
    assert resultado.jogos[0].donos_estimados
    assert resultado.jogos[0].tags_comunidade
    assert len(resultado.noticias) == 3


# ---------------------------------------------------------------------- midias


def test_midias_poem_video_antes_de_imagem():
    """O carrossel abre pelo trailer - a captura entra como continuacao."""
    midias = _parse_midias(
        {
            "screenshots": [{"path_full": "https://img/1.jpg"}],
            "movies": [
                {
                    "name": "Trailer",
                    "thumbnail": "https://img/cartaz.jpg",
                    "hls_h264": "https://video/hls.m3u8",
                }
            ],
        }
    )

    assert [m["tipo"] for m in midias] == ["video", "imagem"]
    assert midias[0] == {
        "tipo": "video",
        "url": "https://video/hls.m3u8",
        "cartaz": "https://img/cartaz.jpg",
        "titulo": "Trailer",
    }


def test_midias_ignoram_video_sem_hls():
    """A Steam nao publica mais mp4/webm; video sem HLS nao toca em navegador
    nenhum, entao nao entra no carrossel (ficaria um slot morto)."""
    midias = _parse_midias(
        {
            "movies": [
                {"name": "So dash", "dash_h264": "https://video/x.mpd"},
                {"name": "Com hls", "hls_h264": "https://video/ok.m3u8"},
            ]
        }
    )

    assert [m["titulo"] for m in midias] == ["Com hls"]


def test_midias_respeitam_o_teto_por_tipo():
    midias = _parse_midias(
        {
            "movies": [
                {"name": f"v{i}", "hls_h264": f"https://video/{i}.m3u8"} for i in range(5)
            ],
            "screenshots": [{"path_full": f"https://img/{i}.jpg"} for i in range(20)],
        }
    )

    tipos = [m["tipo"] for m in midias]
    assert tipos.count("video") == 2
    assert tipos.count("imagem") == 8


def test_midias_vazias_quando_o_jogo_nao_tem_galeria():
    assert _parse_midias({}) == []
