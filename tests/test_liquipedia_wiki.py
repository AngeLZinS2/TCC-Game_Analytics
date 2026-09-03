"""Testes do parser de wikitexto das equipes da Liquipedia.

A fixture e um payload real reduzido, e as quatro paginas nela nao foram
escolhidas por serem as primeiras: cada uma cobre um caso que ja quebrou algo.

* **Team Spirit** - equipe ativa. O wikitexto fecha `|disbanded=}}` na MESMA
  linha, e foi esse formato que fez a primeira tentativa (um regex
  `[^\\n|]*`) devolver `}}` como se fosse a data de dissolucao. Tambem tem
  `{{Team|...}}` aninhado dentro de um parametro, com `|` dentro.
* **1st.VN** - dissolvida com data PARCIAL (`2014-??-??`).
* **2Be Continued Esports** - dissolvida com data completa.
* **Absolute Legends** - sem `teamid`. Depois que o projeto passou a cobrir
  as 73 wikis, ela deixou de ser descarte e virou o caso normal: identidade
  pelo titulo da pagina.

Se a Liquipedia mudar o nome de um campo do infobox, estes testes falham antes
de a dimensao ficar com regiao nula em silencio.
"""

from __future__ import annotations

import pytest

from etl.transform_liquipedia_wiki import (
    EquipeWiki,
    campos_do_template,
    parse_equipe,
    transformar,
)


@pytest.fixture(scope="module")
def payload(carregar_fixture):
    return carregar_fixture("liquipedia_equipes")


@pytest.fixture(scope="module")
def equipes(payload) -> dict[str, EquipeWiki]:
    return {e.nome: e for e in transformar(payload).equipes}


# ------------------------------------------------- o parser de template


def test_corta_so_nos_pipes_do_nivel_de_cima():
    """`|` dentro de `{{}}` ou `[[]]` faz parte do valor, nao separa campo."""
    texto = "{{Infobox team\n|name=X\n|parceiro={{Link|a|b}}\n|local=[[Brasil|BR]]\n}}"
    campos = campos_do_template(texto, "Infobox team")

    assert campos["name"] == "X"
    assert campos["parceiro"] == "{{Link|a|b}}"
    assert campos["local"] == "[[Brasil|BR]]"


def test_campo_vazio_nao_engole_o_fechamento():
    """O caso que quebrou o regex: `|disbanded=}}` na mesma linha.

    Um `[^\\n|]*` devolve `}}` aqui, e a equipe ativa vira "dissolvida em }}".
    """
    campos = campos_do_template("{{Infobox team|name=X|disbanded=}}", "Infobox team")

    assert campos["name"] == "X"
    assert campos["disbanded"] == ""


def test_template_ausente_devolve_vazio():
    """Pagina sem infobox existe (esboco, redirecionamento) e nao e erro."""
    assert campos_do_template("#REDIRECT [[Outra]]", "Infobox team") == {}


# ----------------------------------------------------- o parse da equipe


def test_equipe_ativa_vem_com_teamid_e_regiao(equipes):
    spirit = equipes["Team Spirit"]

    # Na wiki de Dota 2 a identidade e o teamid: o mesmo numero que a OpenDota
    # publica, e o que permite ligar sem casar nome com nome.
    assert spirit.id_externo == "7119388"
    assert spirit.ativa is True
    assert spirit.regiao == "CIS"
    assert spirit.pagina == "Team Spirit"


def test_regiao_e_normalizada(equipes):
    """A wiki escreve `cis`, `CIS` e `Commonwealth of Independent States`.

    Sem normalizar, um agrupamento por regiao mostraria a mesma regiao em tres
    linhas diferentes.
    """
    assert all(
        e.regiao in (None, "CIS", "Southeast Asia", "Europe", "North America",
                     "South America", "China", "Oceania", "Africa",
                     "Middle East", "South Asia")
        for e in equipes.values()
    )


def test_data_parcial_vira_nulo():
    """`2014-??-??` nao e uma data - completar o `??` inventaria precisao."""
    texto = "{{Infobox team|name=X|teamid=1|created=2014-??-??|disbanded=}}"
    equipe = parse_equipe("X", texto)

    assert equipe is not None
    assert equipe.criada_em is None


def test_data_completa_e_lida():
    texto = "{{Infobox team|name=X|teamid=1|created=2015-12-06|disbanded=}}"
    equipe = parse_equipe("X", texto)

    assert equipe is not None
    assert equipe.criada_em is not None
    assert equipe.criada_em.year == 2015


def test_disbanded_preenchido_marca_inativa(equipes):
    inativas = [e for e in equipes.values() if e.ativa is False]
    assert inativas, "a fixture tem equipes dissolvidas"


def test_sem_teamid_a_identidade_e_a_pagina():
    """Fora do Dota o infobox nao tem `teamid`, e isso nao pode descartar tudo.

    Foi medido: em counterstrike, valorant, leagueoflegends e rocketleague o
    `{{Infobox team}}` traz `name`, `region`, `location`, `created` e
    `disbanded`, e nada mais. A versao anterior deste parser exigia `teamid` e
    teria descartado 100% das equipes dessas 70 wikis EM SILENCIO - o coletor
    diria "0 equipes" e nada pareceria quebrado.
    """
    texto = "{{Infobox team|name=100 Thieves|region=North America|disbanded=}}"
    equipe = parse_equipe("100 Thieves", texto)

    assert equipe is not None
    assert equipe.id_externo == "100 Thieves"
    assert equipe.regiao == "North America"


def test_pagina_sem_infobox_e_descartada(payload):
    """So a ausencia do proprio infobox descarta - ai nao ha o que ler."""
    equipe = parse_equipe("Alguma", "#REDIRECT [[Outra]]")
    assert equipe is None

    # A fixture tem uma pagina sem `teamid`; ela agora ENTRA, identificada
    # pelo titulo, em vez de sumir.
    nomes = {e.nome for e in transformar(payload).equipes}
    assert "Absolute Legends" in nomes


# ----------------------------------------------------------- o transform


def test_transformar_ignora_payload_de_outro_formato():
    """O `--from-raw` entrega os payloads da agenda junto dos de equipe."""
    assert transformar({"parse": {"text": {"*": "<html>"}}}).total == 0
    assert transformar(None).total == 0
    assert transformar({"query": {}}).total == 0


def test_transformar_deduplica_por_teamid():
    """Redirecionamentos e paginas de organizacao apontam ao mesmo teamid.

    Duas linhas com o mesmo id quebrariam o upsert com CardinalityViolation -
    foi o que aconteceu de verdade na carga da agenda.
    """
    infobox = "{{Infobox team|name=%s|teamid=99|disbanded=}}"
    payload = {
        "query": {
            "pages": {
                "1": {"title": "A", "revisions": [{"slots": {"main": {"*": infobox % "A"}}}]},
                "2": {"title": "B", "revisions": [{"slots": {"main": {"*": infobox % "B"}}}]},
            }
        }
    }
    assert transformar(payload).total == 1


def test_pagina_sem_revisao_nao_quebra():
    """Pagina apagada entre o indice e a leitura vem sem `revisions`."""
    payload = {"query": {"pages": {"1": {"title": "Sumiu"}}}}
    assert transformar(payload).total == 0
