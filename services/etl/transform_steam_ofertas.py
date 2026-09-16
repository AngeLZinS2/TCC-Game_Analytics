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

**Tipo do app.** O fragmento HTML nao diz se a linha e jogo, DLC ou trilha
sonora - nada no `search_result_row` distingue os tres. Quem distingue e o
proprio buscador, pelo parametro `category1` (998 = jogo, 21 = DLC),
conferido ao vivo em 2026-09-16: 19.963 ofertas no total, 9.428 com
`category1=998` e 9.202 com `category1=21`. Por isso `parse_pagina` recebe
o tipo de fora - nao e heuristica sobre o nome ("Soundtrack", "DLC"), que
erraria em jogo chamado "DLC Quest" e em DLC sem a palavra no titulo.
"""

from __future__ import annotations

import json
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


#: Os dois tipos que a varredura cobre, no MESMO vocabulario que o
#: `appdetails` usa em `dim_jogo_steam.tipo` - assim as duas fontes escrevem
#: o mesmo valor e nada precisa traduzir entre elas.
TIPO_JOGO = "game"
TIPO_DLC = "dlc"


@dataclass(slots=True)
class LinhaOfertaSteam:
    app_id: int
    nome: str
    preco_final_centavos: int
    preco_original_centavos: int
    desconto_percentual: int
    #: `TIPO_JOGO` ou `TIPO_DLC` - de qual `category1` esta linha veio, nao
    #: uma leitura do HTML (ver a nota no topo do modulo).
    tipo: str = TIPO_JOGO
    #: Ids das tags da Steam daquele app (`data-ds-tagids`). Vazio quando a
    #: linha nao traz o atributo. Sao o que sustenta o filtro de genero da
    #: tela de Ofertas: os apps que so existem por causa da varredura nunca
    #: tiveram ficha (`appdetails`) e, portanto, nao tem `generos`.
    tags: list[int] = field(default_factory=list)


@dataclass(slots=True)
class ResultadoOfertasSteam:
    linhas: list[LinhaOfertaSteam] = field(default_factory=list)
    #: `{tag_id: nome}` do dicionario publico da Steam. Vazio quando a
    #: chamada do dicionario falhou - as ofertas seguem valendo, so o
    #: filtro de genero fica sem rotulo novo.
    tags: dict[int, str] = field(default_factory=dict)
    #: `False` quando a varredura parou por erro/trava de seguranca antes de
    #: esgotar as paginas - o load usa isto pra NUNCA encerrar promocoes
    #: ausentes de uma varredura incompleta (ausencia so significa "nao
    #: chegamos la ainda", nao "saiu de promocao").
    completa: bool = True

    @property
    def total(self) -> int:
        return len(self.linhas)


def parse_pagina(results_html: str, tipo: str = TIPO_JOGO) -> list[LinhaOfertaSteam]:
    """Uma pagina do fragmento `results_html` -> linhas validadas.

    `tipo` vem de quem chamou porque e o `category1` da requisicao que sabe
    disso, nao o HTML devolvido.
    """
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
                tipo=tipo,
                tags=_tags(item.get("data-ds-tagids")),
            )
        )

    return linhas


def _tags(bruto: object) -> list[int]:
    """`data-ds-tagids="[122,4747,6426]"` -> `[122, 4747, 6426]`.

    Tolerante de proposito: o atributo pode faltar ou vir vazio, e uma tag
    ilegivel nao pode derrubar a oferta inteira - o preco e o que importa
    naquela linha, a tag e o extra.
    """
    if not isinstance(bruto, str):
        return []
    try:
        valores = json.loads(bruto)
    except ValueError:
        return []
    if not isinstance(valores, list):
        return []
    return [int(v) for v in valores if isinstance(v, int)]


def parse_dicionario_tags(payload: object) -> dict[int, str]:
    """`/tagdata/populartags/<idioma>` -> `{tag_id: nome}`."""
    if not isinstance(payload, list):
        return {}
    dicionario: dict[int, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        tag_id = item.get("tagid")
        nome = item.get("name")
        if isinstance(tag_id, int) and isinstance(nome, str) and nome.strip():
            dicionario[tag_id] = nome.strip()
    return dicionario
