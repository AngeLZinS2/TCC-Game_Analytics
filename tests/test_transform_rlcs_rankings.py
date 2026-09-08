"""Testes do parser do leaderboard da RLCS (blast.tv).

O HTML é um recorte fiel de uma linha do leaderboard renderizado no servidor:
`div.group[data-active]` com `span.min-w-8` (rank), `img[alt$=" logo"]` (time) e
`div.min-w-12 > span` (pontos, que pode ser negativo).
"""

from __future__ import annotations

from etl.transform_rlcs_rankings import parse_leaderboard


def _linha(rank: str, nome: str, pts: str | None) -> str:
    pts_html = (
        f'<div class="flex min-w-12 flex-row justify-center gap-1"><span>{pts}</span>'
        '<span class="text-neutral">pts</span></div>'
        if pts is not None
        else ""
    )
    return (
        '<div class="mb-3 flex w-full flex-col group !m-0" data-active="false">'
        '<div class="h-9 flex flex-row gap-3 px-3">'
        f'<span class="min-w-8">#<!-- -->{rank}</span>'
        f'<div class="flex w-full flex-row items-center gap-3">'
        f'<img class="size-5" alt="{nome} logo" src="https://assets.blast.tv/x"/>'
        f"<span>{nome}</span></div>"
        f"{pts_html}"
        "</div></div>"
    )


PAGINA = (
    '<div class="flex flex-col gap-1">'
    + _linha("1", "Karmine Corp", "112")
    + _linha("2", "Gentle Mates", "101")
    + _linha("3", "Vitality", "97")
    + _linha("36", "100", "0")
    + _linha("44", "Project S", "-3")
    + "</div>"
)


def test_le_rank_time_e_pontos():
    linhas = parse_leaderboard(PAGINA, "europe")
    assert [(l.posicao, l.equipe_nome, l.pontos) for l in linhas] == [
        (1, "Karmine Corp", 112),
        (2, "Gentle Mates", 101),
        (3, "Vitality", 97),
        (36, "100", 0),
        (44, "Project S", -3),
    ]
    assert all(l.regiao == "europe" for l in linhas)


def test_linha_sem_pontos_vira_none():
    html = '<div data-active="false">' + _linha("5", "Team BSK", None) + "</div>"
    linhas = parse_leaderboard(html, "mena")
    assert len(linhas) == 1
    assert linhas[0].pontos is None


def test_pagina_sem_leaderboard_devolve_vazio():
    assert parse_leaderboard("<div>404</div>", "oceania") == []
    assert parse_leaderboard("", "oceania") == []


def test_nao_repete_time():
    html = (
        '<div data-active="false">'
        + _linha("1", "NRG", "90")
        + _linha("1", "NRG", "90")
        + "</div>"
    )
    assert len(parse_leaderboard(html, "north-america")) == 1
