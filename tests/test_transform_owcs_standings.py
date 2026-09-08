"""Testes do parser da classificação do OWCS (Liquipedia).

O HTML aqui é um recorte fiel do `div.group-table-results` que a Liquipedia
renderiza a partir do LPDB: `group-table-rank`, `group-table-entry` com
`team-template-text`, `group-table-match-score`. A página real traz um bloco
desses por semana da temporada - o parser tem de ler só o último.
"""

from __future__ import annotations

from etl.transform_owcs_standings import parse_standings


def _bloco(linhas: str) -> str:
    return f'<div class="group-table-results">{linhas}</div>'


def _linha(rank: str, nome: str, placar: str) -> str:
    return (
        '<div class="group-table-result-row">'
        f'<div class="group-table-cell group-table-rank">{rank}</div>'
        '<div class="group-table-cell group-table-entry brkts-opponent-hover">'
        f'<span class="team-template-text"><a href="/overwatch/{nome.replace(" ", "_")}">{nome}</a></span>'
        "</div>"
        f'<div class="group-table-cell group-table-match-score">{placar}</div>'
        "</div>"
    )


PAGINA = (
    _bloco(_linha("1.", "Spacestation Gaming", "1–0") + _linha("2.", "Dallas Fuel", "0–1"))
    + _bloco(
        _linha("1.", "Spacestation Gaming", "5–0")
        + _linha("2.", "Dallas Fuel", "4–1")
        + _linha("3.", "Team Liquid", "3–2")
        + _linha("4.", "LuneX Gaming", "2–3")
        + _linha("5.", "The Kafe", "1–4")
        + _linha("6.", "Disguised", "0–5")
    )
)


def test_le_a_ultima_tabela_nao_a_primeira():
    linhas = parse_standings(PAGINA, "north-america")
    assert [linha.posicao for linha in linhas] == [1, 2, 3, 4, 5, 6]
    assert linhas[0].equipe_nome == "Spacestation Gaming"
    assert linhas[0].serie_vitorias == 5 and linhas[0].serie_derrotas == 0
    assert linhas[-1].equipe_nome == "Disguised"
    assert all(linha.regiao == "north-america" for linha in linhas)


def test_empate_mantem_a_posicao_repetida():
    html = _bloco(
        _linha("1.", "Virtus.pro", "5–0")
        + _linha("3.", "Geekay Esports", "2–3")
        + _linha("3.", "Al Qadsiah", "2–3")
        + _linha("3.", "1234", "2–3")
        + _linha("6.", "Telacy", "0–5")
    )
    linhas = parse_standings(html, "europe")
    assert [linha.posicao for linha in linhas] == [1, 3, 3, 3, 6]


def test_pagina_sem_tabela_devolve_vazio():
    assert parse_standings("<div>Stage ainda não começou</div>", "china") == []
    assert parse_standings("", "china") == []


def test_ignora_linha_sem_time():
    html = _bloco(
        '<div class="group-table-result-row">'
        '<div class="group-table-cell group-table-rank">1.</div>'
        '<div class="group-table-cell group-table-entry"></div>'
        "</div>"
        + _linha("2.", "Crazy Raccoon", "3–1")
    )
    linhas = parse_standings(html, "japan")
    assert [linha.equipe_nome for linha in linhas] == ["Crazy Raccoon"]
