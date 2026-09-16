"""Parsing do fragmento HTML da busca de ofertas da Steam.

O fragmento e o mesmo que o navegador renderiza em `/specials`; o que este
parser faz e extrair dele preco, desconto e as TAGS do app. As tags sao o que
sustenta o filtro de genero/categoria da tela de Ofertas - sem elas, o filtro
nasceria vazio, porque os ~18 mil apps que so existem por causa da varredura
nunca tiveram ficha (`appdetails`) e, portanto, nao tem `generos`.
"""

from services.etl.transform_steam_ofertas import (
    TIPO_DLC,
    TIPO_JOGO,
    parse_dicionario_tags,
    parse_pagina,
)


def linha(
    app_id: int = 730,
    nome: str = "Counter-Strike 2",
    desconto: int = 50,
    preco_final: int = 2999,
    tagids: str | None = "[1663,19,3859]",
) -> str:
    atributo = f' data-ds-tagids="{tagids}"' if tagids is not None else ""
    return f"""
    <a href="/app/{app_id}/" data-ds-appid="{app_id}"{atributo}>
      <div class="responsive_search_name_combined">
        <div class="search_name"><span class="title">{nome}</span></div>
        <div class="discount_block search_discount_block"
             data-price-final="{preco_final}" data-discount="{desconto}"></div>
      </div>
    </a>
    """


def test_extrai_tags_do_atributo_da_linha():
    (oferta,) = parse_pagina(linha())
    assert oferta.app_id == 730
    assert oferta.tags == [1663, 19, 3859]


def test_linha_sem_tags_nao_derruba_a_oferta():
    """A tag e o extra; o preco e o motivo da linha existir."""
    (oferta,) = parse_pagina(linha(tagids=None))
    assert oferta.tags == []
    assert oferta.preco_final_centavos == 2999


def test_tags_ilegiveis_viram_lista_vazia():
    (oferta,) = parse_pagina(linha(tagids="nao-e-json"))
    assert oferta.tags == []


def test_preco_original_reconstruido_do_desconto():
    """A Steam nao publica o preco cheio em centavos no HTML - so o texto
    localizado. O original sai do final + desconto."""
    (oferta,) = parse_pagina(linha(desconto=50, preco_final=2999))
    assert oferta.preco_original_centavos == 5998


def test_desconto_de_100_fica_de_fora():
    """Item de graca: `preco_final=0` quebraria a reconstrucao (divisao por
    zero) - visto ao vivo em 2026-09-15."""
    assert parse_pagina(linha(desconto=100, preco_final=0)) == []


def test_dicionario_de_tags():
    payload = [
        {"tagid": 19, "name": "Ação"},
        {"tagid": 122, "name": "RPG"},
        {"tagid": 9, "name": "  "},  # nome vazio - descartado
        {"naoTag": True},
    ]
    assert parse_dicionario_tags(payload) == {19: "Ação", 122: "RPG"}


def test_dicionario_de_tags_com_payload_invalido():
    assert parse_dicionario_tags(None) == {}
    assert parse_dicionario_tags({"erro": "nope"}) == {}


def test_paginas_repetem_o_mesmo_app():
    """A Steam reordena a lista entre uma pagina e outra da varredura, entao
    o mesmo app reaparece - medido: 19.393 linhas para ~18.000 apps. O parser
    nao tenta resolver isso (cada pagina e lida isolada); quem deduplica e o
    load, e este teste fixa a premissa de que duplicata CHEGA ate ele."""
    pagina1 = parse_pagina(linha(app_id=730, preco_final=2999))
    pagina2 = parse_pagina(linha(app_id=730, preco_final=1999))
    juntas = pagina1 + pagina2
    assert [o.app_id for o in juntas] == [730, 730]
    # A ultima leitura e a que o load mantem.
    assert juntas[-1].preco_final_centavos == 1999


def test_tipo_vem_de_quem_chamou_nao_do_html():
    """O fragmento HTML nao distingue jogo de DLC - nada no
    `search_result_row` diz o que o app e. Quem sabe e o `category1` da
    requisicao (998 = jogo, 21 = DLC), entao o tipo entra por parametro.

    E a razao de nao ser heuristica de nome: o MESMO HTML vira jogo ou DLC
    dependendo so de qual varredura o trouxe."""
    html = linha(app_id=730, nome="Counter-Strike 2")
    (jogo,) = parse_pagina(html, tipo=TIPO_JOGO)
    (dlc,) = parse_pagina(html, tipo=TIPO_DLC)
    assert jogo.tipo == TIPO_JOGO
    assert dlc.tipo == TIPO_DLC


def test_tipo_padrao_e_jogo():
    """Chamada sem tipo (raw gravado antes da separacao por `category1`, em
    2026-09-16) e lida como jogo - era o que a varredura unica
    majoritariamente trazia. Reprocessar raw antigo nao pode quebrar."""
    (oferta,) = parse_pagina(linha())
    assert oferta.tipo == TIPO_JOGO


def test_nome_nao_decide_o_tipo():
    """Fixa a premissa oposta a heuristica de nome: "DLC Quest" e um JOGO, e
    uma DLC pode nao ter a palavra no titulo. So o `category1` decide."""
    (jogo,) = parse_pagina(linha(nome="DLC Quest"), tipo=TIPO_JOGO)
    assert jogo.tipo == TIPO_JOGO
    (dlc,) = parse_pagina(linha(nome="End of Zoe"), tipo=TIPO_DLC)
    assert dlc.tipo == TIPO_DLC
