"""Normalizacao do cenario de LoL profissional (classificacao + elenco).

Sem rede, sem banco: os payloads de `getStandings` e `getTeams` que a suite
capturou em `tests/fixtures/` passam pelo `transformar` puro.
"""

from __future__ import annotations

from services.collectors.base import RawRecord
from services.etl.transform_lol_cenario import (
    ENDPOINT_STANDINGS,
    ENDPOINT_TEAM,
    transformar,
)


def _registros(carregar_fixture):
    return [
        RawRecord(
            fonte="lolesports",
            endpoint=ENDPOINT_STANDINGS,
            identificador="lec",
            payload=carregar_fixture("lolesports_getstandings_lec"),
        ),
        RawRecord(
            fonte="lolesports",
            endpoint=ENDPOINT_TEAM,
            identificador="karmine-corp",
            payload=carregar_fixture("lolesports_getteams_kc"),
        ),
    ]


def test_standings_viram_linhas_de_ranking_com_vitorias_e_derrotas(carregar_fixture):
    resultado = transformar(_registros(carregar_fixture))

    por_nome = {linha.equipe_nome: linha for linha in resultado.linhas_ranking}
    kc = por_nome["Karmine Corp"]
    assert kc.posicao == 1
    assert (kc.vitorias, kc.derrotas) == (9, 0)
    assert kc.regiao == "lec"
    # a secao de playoffs (rankings vazio) nao entra
    assert len(resultado.linhas_ranking) == 10


def test_getteams_vira_equipe_e_elenco(carregar_fixture):
    resultado = transformar(_registros(carregar_fixture))

    assert len(resultado.equipes) == 1
    equipe = resultado.equipes[0]
    assert equipe.id_externo == "lolesports:111692118851466302"
    assert equipe.nome == "Karmine Corp"
    assert equipe.tag == "KC"
    assert equipe.regiao == "lec"

    por_apelido = {j.nome: j for j in resultado.jogadores}
    assert set(por_apelido) == {"Canna", "Yike", "Caliste", "kyeahoo", "Busio"}
    canna = por_apelido["Canna"]
    assert canna.id_externo == "103495716771322725"
    assert canna.nome_completo == "Changdong Kim"
    assert canna.papel == "top"
    assert canna.imagem
    assert canna.equipe_id_externo == equipe.id_externo


def test_registro_de_outra_fonte_e_ignorado(carregar_fixture):
    registros = _registros(carregar_fixture)
    registros.append(
        RawRecord(
            fonte="pandascore",
            endpoint=ENDPOINT_STANDINGS,
            identificador="lec",
            payload=carregar_fixture("lolesports_getstandings_lec"),
        )
    )
    resultado = transformar(registros)
    # nao dobrou as linhas
    assert len(resultado.linhas_ranking) == 10
