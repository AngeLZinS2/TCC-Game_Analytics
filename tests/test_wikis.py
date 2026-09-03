"""Testes do registro de wikis da Liquipedia.

O registro nao e uma lista escrita a mao: saiu de uma varredura em que cada
wiki foi perguntada se tem `Liquipedia:Matches` e se `Category:Teams` tem
membros. Estes testes protegem as invariantes que a varredura estabeleceu, e
que um `git merge` descuidado quebraria sem barulho.
"""

from __future__ import annotations

import json

from etl.wikis import ARQUIVO_REGISTRO, Wiki, com_agenda, com_times, por_codigo, registro


def test_o_registro_carrega_e_nao_esta_vazio():
    assert len(registro()) >= 70


def test_toda_wiki_serve_para_alguma_coisa():
    """Uma wiki sem agenda E sem times so ocuparia uma linha em `dim_jogo`.

    `illuvium` foi exatamente esse caso na varredura, e por isso ficou fora.
    """
    inuteis = [w.codigo for w in registro() if not w.agenda and not w.times]
    assert inuteis == []


def test_codigos_sao_unicos():
    codigos = [w.codigo for w in registro()]
    assert len(codigos) == len(set(codigos))


def test_wikis_meta_ficam_de_fora():
    """`commons`, `hub`, `lab` e afins nao sao jogos.

    Entrariam em `dim_jogo` e apareceriam num seletor de jogos do dashboard,
    prometendo uma tela que nunca teria dado.
    """
    codigos = {w.codigo for w in registro()}
    assert not (codigos & {"commons", "hub", "lab", "esports", "dota2gamearchive"})


def test_codigo_cabe_na_coluna():
    """`dim_jogo.codigo` e `String(32)` depois da migration 0008.

    Antes era 16, e `leagueoflegends` tem 15 - passava raspando.
    """
    assert max(len(w.codigo) for w in registro()) <= 32


def test_nome_cabe_na_coluna():
    """`dim_jogo.nome` e `String(64)`."""
    assert max(len(w.nome) for w in registro()) <= 64


def test_dota2_esta_no_registro_com_as_duas_capacidades():
    dota = por_codigo("dota2")
    assert dota is not None
    assert dota.agenda and dota.times


def test_jogos_individuais_nao_tem_agenda():
    """Smash, StarCraft, Fighting Games e Formula 1 nao tem `Liquipedia:Matches`.

    Nao e falha da varredura: sao competicoes INDIVIDUAIS, onde quem se
    enfrenta e pessoa e nao equipe, e a wiki organiza o calendario de outro
    jeito. Se um dia passarem a ter, este teste avisa que o registro precisa
    ser regerado.
    """
    for codigo in ("smash", "starcraft", "fighters", "formula1"):
        wiki = por_codigo(codigo)
        assert wiki is not None, codigo
        assert not wiki.agenda, f"{codigo} passou a ter agenda - regerar o registro"


def test_url_da_api_e_montada_a_partir_do_codigo():
    assert por_codigo("valorant").url_api == "https://liquipedia.net/valorant/api.php"


def test_recortes_sao_subconjuntos_do_registro():
    todos = set(registro())
    assert set(com_agenda()) <= todos
    assert set(com_times()) <= todos
    assert all(w.agenda for w in com_agenda())
    assert all(w.times for w in com_times())


def test_o_arquivo_e_json_valido_com_as_chaves_esperadas():
    """O registro e versionado; um editor desatento pode quebrar o formato."""
    dados = json.loads(ARQUIVO_REGISTRO.read_text(encoding="utf-8"))
    assert isinstance(dados, list)
    for item in dados:
        assert set(item) == {"codigo", "nome", "agenda", "times"}, item


def test_wiki_e_imutavel():
    """`registro()` e cacheado; um Wiki mutavel deixaria o cache mentir."""
    wiki = Wiki(codigo="x", nome="X", agenda=True, times=True)
    try:
        wiki.codigo = "y"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Wiki deveria ser frozen")
