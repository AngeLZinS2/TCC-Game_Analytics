"""Testes da serie minuto a minuto coletada das partidas.

O modelo que consumia esta serie saiu do projeto junto das telas dele, mas o
parser ficou: a tabela `fato_minuto_partida` continua sendo preenchida, e
`data/raw/` continua guardando o payload que a origina. Estes testes seguem
sendo o contrato com a OpenDota - se `radiant_gold_adv` deixar de vir indexado
por minuto, ou se a chave de `building_kill` mudar de formato, eles falham
antes de o dado errado entrar no banco.

A fixture e a partida 8979484553 reduzida aos campos que `parse_serie_minutos`
consome.
"""

from __future__ import annotations

import pytest

from etl.transform_dota import parse_serie_minutos


@pytest.fixture(scope="module")
def payload(carregar_fixture):
    return carregar_fixture("opendota_match_serie")


@pytest.fixture(scope="module")
def serie(payload):
    return parse_serie_minutos(payload)


def test_um_ponto_por_minuto_da_curva(payload, serie):
    """O indice de `radiant_gold_adv` E o minuto: uma linha para cada."""
    assert len(serie) == len(payload["radiant_gold_adv"])
    assert [linha.minuto for linha in serie] == list(range(len(serie)))


def test_vantagens_saem_da_curva_sem_reordenar(payload, serie):
    assert [linha.vantagem_economia for linha in serie] == payload["radiant_gold_adv"]
    assert [linha.vantagem_experiencia for linha in serie] == payload["radiant_xp_adv"]


def test_rotulo_repete_o_desfecho_em_todas_as_linhas(payload, serie):
    """O alvo do treino e o desfecho da partida, igual em cada minuto dela."""
    esperado = payload["radiant_win"]
    assert {linha.vitoria_lado_a for linha in serie} == {esperado}


def test_torres_sao_acumuladas_e_nunca_decrescem(serie):
    """Estado do mapa e cumulativo: torre destruida nao volta."""
    for anterior, atual in zip(serie, serie[1:]):
        assert atual.torres_perdidas_lado_a >= anterior.torres_perdidas_lado_a
        assert atual.torres_perdidas_lado_b >= anterior.torres_perdidas_lado_b
        assert atual.objetivos_maiores_lado_a >= anterior.objetivos_maiores_lado_a
        assert atual.objetivos_maiores_lado_b >= anterior.objetivos_maiores_lado_b


def test_lado_da_torre_vem_da_chave_da_construcao(payload, serie):
    """`goodguys` na chave e torre do lado A; `badguys`, do lado B.

    A chave nomeia a construcao DESTRUIDA - trocar os dois lados aqui inverteria
    o sinal da feature mais importante do modelo sem quebrar nada.
    """
    torres = [
        evento
        for evento in payload["objectives"]
        if evento.get("type") == "building_kill" and "tower" in str(evento.get("key"))
    ]
    esperado_a = sum(1 for e in torres if "goodguys" in e["key"])
    esperado_b = sum(1 for e in torres if "badguys" in e["key"])

    assert serie[-1].torres_perdidas_lado_a == esperado_a
    assert serie[-1].torres_perdidas_lado_b == esperado_b


def test_racks_e_fort_nao_contam_como_torre(payload):
    """So `tower` entra: barracks e fort sao outra coisa no mapa."""
    tem_rax = any(
        "rax" in str(e.get("key")) or "fort" in str(e.get("key"))
        for e in payload["objectives"]
    )
    assert tem_rax, "fixture precisa ter rax/fort para o teste valer"

    serie = parse_serie_minutos(payload)
    total_torres = serie[-1].torres_perdidas_lado_a + serie[-1].torres_perdidas_lado_b
    total_eventos_construcao = sum(
        1 for e in payload["objectives"] if e.get("type") == "building_kill"
    )
    assert total_torres < total_eventos_construcao


def test_payload_sem_curva_nao_gera_serie():
    """Partida sem replay parseado pela OpenDota: nao ha o que treinar."""
    assert parse_serie_minutos({"match_id": 1, "radiant_win": True}) == []
    assert parse_serie_minutos({"match_id": 1, "radiant_gold_adv": []}) == []


def test_payload_invalido_nao_levanta():
    assert parse_serie_minutos(None) == []
    assert parse_serie_minutos("nao e dicionario") == []
    assert parse_serie_minutos({"radiant_gold_adv": [0, 1]}) == []  # sem match_id


def test_xp_mais_curto_que_ouro_vira_nulo():
    """Curvas de tamanhos diferentes nao podem estourar o indice."""
    serie = parse_serie_minutos(
        {
            "match_id": 7,
            "radiant_win": False,
            "radiant_gold_adv": [0, 100, 200],
            "radiant_xp_adv": [0, 50],
        }
    )
    assert [linha.vantagem_experiencia for linha in serie] == [0, 50, None]
    assert len(serie) == 3
