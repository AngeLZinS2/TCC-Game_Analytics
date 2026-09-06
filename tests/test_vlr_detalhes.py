"""Testes do parser do detalhe de partida do vlr.gg.

Sem rede: a fixture `vlr_partida_734314.html` e um recorte fiel da pagina
`/734314/x` (NRG 2-3 LOUD) - a navegacao de mapas, o bloco do mapa 1 (Abyss),
o bloco agregado da serie (`data-game-id="all"`, que NAO deve virar um mapa) e
o bloco do mapa 2 (Sunset). O que se protege e o contrato com o markup: se o
vlr.gg mexer nas classes, este e o ponto que quebra primeiro, nao a tela.
"""

from __future__ import annotations

from pathlib import Path

from collectors.vlr_detalhes import _parse_partida

_HTML = (Path(__file__).resolve().parent / "fixtures" / "vlr_partida_734314.html").read_text(
    encoding="utf-8"
)


def test_extrai_os_mapas_ignorando_o_agregado_da_serie():
    d = _parse_partida(_HTML)

    assert d["fonte"] == "vlr.gg"
    # A fixture tem 3 blocos: Abyss, `all`, Sunset. O `all` fica de fora.
    assert [m["nome"] for m in d["mapas"]] == ["Abyss", "Sunset"]


def test_placar_e_duracao_por_mapa():
    d = _parse_partida(_HTML)
    abyss = d["mapas"][0]

    # NRG perdeu Abyss 10-13.
    assert (abyss["placar_a"], abyss["placar_b"]) == (10, 13)
    assert abyss["duracao"] and ":" in abyss["duracao"]


def test_dez_jogadores_por_mapa_com_stats():
    d = _parse_partida(_HTML)
    abyss = d["mapas"][0]

    assert len(abyss["jogadores"]) == 10
    # Cinco de cada time.
    times = {j["time"] for j in abyss["jogadores"]}
    assert len(times) == 2

    j = abyss["jogadores"][0]
    assert j["nome"]
    assert j["agente"]
    # ACS e K/D/A vem preenchidos; sao numeros.
    assert isinstance(j["acs"], (int, float))
    assert isinstance(j["k"], int)
    assert isinstance(j["d"], int)
    assert isinstance(j["a"], int)


def test_pagina_sem_bloco_de_mapa_volta_vazia():
    d = _parse_partida("<html><body>manutencao</body></html>")
    assert d == {"fonte": "vlr.gg", "mapas": []}
