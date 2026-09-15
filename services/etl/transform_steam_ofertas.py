"""Parsing puro da varredura completa de ofertas da Steam (Fase 35.1).

A pagina `/specials` da Steam e so a vitrine - quem traz os dados e uma
chamada AJAX pro proprio buscador da loja
(`/search/results/?specials=1&infinite=1`), paginada, devolvendo um
fragmento HTML por pagina (nao JSON estruturado por item). E o mesmo
fragmento que o navegador do usuario renderiza direto na tela; este parser
so extrai o que ja esta la, sem heuristica.

Cada `search_result_row` com um `search_discount_block` e uma oferta de item
UNICO (app_id no `data-ds-appid`) com desconto agora. Pacotes/bundles nesta
busca tambem usam `data-ds-appid`, mas sem transacionar preco por app -
descartados por nao terem o bloco de desconto no formato esperado (unico
sinal confiavel sem pedir outro endpoint).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup

FONTE = "steam_ofertas"


def _inteiro(valor: str | None) -> int | None:
    if valor is None:
        return None
    try:
        return int(valor)
    except ValueError:
        return None


@dataclass(slots=True)
class LinhaOfertaSteam:
    app_id: int
    nome: str
    preco_final_centavos: int
    preco_original_centavos: int
    desconto_percentual: int


@dataclass(slots=True)
class ResultadoOfertasSteam:
    linhas: list[LinhaOfertaSteam] = field(default_factory=list)
    #: `False` quando a varredura parou por erro/trava de seguranca antes de
    #: esgotar as paginas - o load usa isto pra NUNCA encerrar promocoes
    #: ausentes de uma varredura incompleta (ausencia so significa "nao
    #: chegamos la ainda", nao "saiu de promocao").
    completa: bool = True

    @property
    def total(self) -> int:
        return len(self.linhas)


def parse_pagina(results_html: str) -> list[LinhaOfertaSteam]:
    """Uma pagina do fragmento `results_html` -> linhas validadas."""
    soup = BeautifulSoup(results_html, "html.parser")
    linhas: list[LinhaOfertaSteam] = []

    for item in soup.select("a[data-ds-appid]"):
        app_id = _inteiro(item.get("data-ds-appid"))
        if app_id is None:
            continue

        nome_el = item.select_one(".search_name .title")
        nome = nome_el.get_text(strip=True) if nome_el else None
        if not nome:
            continue

        # So o bloco de desconto de ITEM proprio conta - e o unico sinal
        # confiavel de "app com preco em desconto agora" neste fragmento
        # (pacotes tambem levam `data-ds-appid`, mas sem este bloco).
        desconto_el = item.select_one(".search_discount_block")
        if desconto_el is None:
            continue

        desconto = _inteiro(desconto_el.get("data-discount"))
        preco_final = _inteiro(desconto_el.get("data-price-final"))
        # `desconto=100` (item de graca, tipo giveaway) faz `preco_final=0`
        # e quebra a reconstrucao abaixo (divisao por zero) - visto ao vivo
        # em 2026-09-15. Sem o preco original em centavos no HTML pra esse
        # caso (so o texto localizado), a linha fica de fora.
        if not desconto or preco_final is None or desconto >= 100:
            continue

        # A Steam nao expoe o preco cheio em centavos no HTML (so o texto
        # localizado, ex. "R$229,90" - dificil de re-parsear com seguranca
        # entre moedas). Reconstruido do desconto, que e sempre inteiro.
        preco_original = round(preco_final / (1 - desconto / 100))

        linhas.append(
            LinhaOfertaSteam(
                app_id=app_id,
                nome=nome,
                preco_final_centavos=preco_final,
                preco_original_centavos=preco_original,
                desconto_percentual=desconto,
            )
        )

    return linhas
