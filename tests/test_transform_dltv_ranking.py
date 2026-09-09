"""Testes do parser do ranking mundial de Dota 2 do DLTV.

O HTML é um recorte fiel de `.ranking__list-case__item`: `.item__info-num`
(rank), `.item__info-logo` com `data-theme-dark` (logo), `.item__info-team__name`
com `.name` e `.points` ("(1,849 Pontos)").
"""

from __future__ import annotations

from services.etl.transform_dltv_ranking import parse_ranking


def _item(num: str, nome: str, pontos: str | None, logo: str | None = "x.webp") -> str:
    logo_html = (
        f'<a class="item__info-logo" data-theme-dark="{logo}"></a>' if logo else ""
    )
    pts_html = (
        f'<div class="points">({pontos} Pontos)</div>' if pontos is not None else ""
    )
    return (
        '<div class="ranking__list-case__item">'
        '<div class="item__info">'
        f'<div class="item__info-num">{num}</div>'
        f"{logo_html}"
        '<div class="item__info-team">'
        f'<a class="item__info-team__name"><div class="name">{nome}</div>{pts_html}</a>'
        "</div></div></div>"
    )


PAGINA = (
    '<div class="ranking__list-case">'
    + _item("#1", "PARIVISION", "1,849")
    + _item("#2", "Team Spirit", "1,316")
    + _item("#3", "Team Yandex", "1,260")
    + "</div>"
)


def test_le_rank_nome_e_pontos():
    linhas = parse_ranking(PAGINA)
    assert [(l.posicao, l.equipe_nome, l.pontos) for l in linhas] == [
        (1, "PARIVISION", 1849),
        (2, "Team Spirit", 1316),
        (3, "Team Yandex", 1260),
    ]
    assert linhas[0].logo_url == "x.webp"


def test_item_sem_pontos_vira_none():
    linhas = parse_ranking('<div class="ranking__list-case">' + _item("#7", "OG", None) + "</div>")
    assert len(linhas) == 1
    assert linhas[0].pontos is None


def test_pagina_sem_ranking_devolve_vazio():
    assert parse_ranking("<div>manutenção</div>") == []
    assert parse_ranking("") == []


def test_nao_repete_time():
    html = (
        '<div class="ranking__list-case">'
        + _item("#1", "PARIVISION", "1,849")
        + _item("#1", "PARIVISION", "1,849")
        + "</div>"
    )
    assert len(parse_ranking(html)) == 1
