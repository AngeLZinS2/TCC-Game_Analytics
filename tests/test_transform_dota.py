"""Testes do ETL do OpenDota.

As fixtures sao payloads reais (reduzidos aos campos que o ETL consome) e
funcionam como contrato: se o OpenDota renomear um campo, o teste falha antes
de o dado sujo chegar ao star schema.

A partida 8979484553 e uma partida profissional real: Team Synapse vs.
4ikibamboni, EPL Masters 2026, vitoria do Radiant em 2097 segundos.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from collectors.base import RawRecord
from etl.transform_dota import (
    ENDPOINT_HEROIS,
    ENDPOINT_LISTA,
    ENDPOINT_PARTIDA,
    chave_tempo,
    epoch_para_datetime,
    nome_do_modo,
    parse_herois,
    parse_partida,
    parse_participacoes,
    transformar,
)

PARTIDA_REAL = "opendota_match_8979484553"
INICIO = datetime(2026, 9, 2, 17, 7, tzinfo=timezone.utc)


def _registro(endpoint: str, identificador: str, payload) -> RawRecord:
    return RawRecord(
        fonte="opendota",
        endpoint=endpoint,
        identificador=identificador,
        payload=payload,
        coletado_em=INICIO,
    )


# --- /heroes ---------------------------------------------------------------


def test_parse_herois(carregar_fixture):
    personagens = parse_herois(carregar_fixture("opendota_heroes"))

    assert len(personagens) == 8
    antimage = personagens[0]
    assert antimage.id_externo == "1"
    assert antimage.nome == "Anti-Mage"
    assert antimage.nome_interno == "npc_dota_hero_antimage"


def test_parse_herois_payload_invalido():
    assert parse_herois(None) == []
    assert parse_herois({"erro": "rate limit"}) == []
    # Entradas malformadas sao descartadas individualmente.
    assert parse_herois([{"id": 1}, {"localized_name": "Sem id"}]) == []


# --- dimensao de partida ---------------------------------------------------


def test_parse_partida(carregar_fixture):
    partida = parse_partida(carregar_fixture(PARTIDA_REAL))

    assert partida is not None
    assert partida.id_externo == "8979484553"
    assert partida.data_inicio == INICIO
    assert partida.id_tempo == 20260902
    assert partida.duracao_segundos == 2097
    assert partida.modo == "captains mode"
    assert partida.tipo_partida == "profissional"
    assert partida.patch == "60"
    assert partida.liga_nome == "EPL Masters 2026 "
    assert partida.liga_id_externo == "19944"


def test_parse_partida_sem_match_id():
    assert parse_partida({"duration": 100}) is None
    assert parse_partida(None) is None


def test_modo_desconhecido_nao_vira_nulo(carregar_fixture):
    """Um game_mode novo do Dota nao pode apagar a informacao."""
    partida = parse_partida(carregar_fixture("opendota_match_anonimo"))
    assert partida is not None
    assert partida.modo == "modo_99"


# --- fato ------------------------------------------------------------------


def test_participacoes_geram_uma_linha_por_jogador(carregar_fixture):
    participacoes, jogadores = parse_participacoes(carregar_fixture(PARTIDA_REAL))

    assert len(participacoes) == 10
    assert len(jogadores) == 10
    assert [p.slot for p in participacoes] == [0, 1, 2, 3, 4, 128, 129, 130, 131, 132]


def test_metricas_do_jogador(carregar_fixture):
    participacoes, _ = parse_participacoes(carregar_fixture(PARTIDA_REAL))
    primeiro = participacoes[0]

    assert primeiro.id_partida_externo == "8979484553"
    assert primeiro.id_jogador_externo == "917164766"
    assert primeiro.id_personagem_externo == "76"
    assert primeiro.equipe == "radiant"
    assert primeiro.vitoria is True
    assert (primeiro.kills, primeiro.deaths, primeiro.assists) == (5, 2, 12)
    assert primeiro.dano_causado == 14568
    assert primeiro.economia == 17230
    assert primeiro.economia_por_minuto == 493
    assert primeiro.experiencia_por_minuto == 539
    assert primeiro.last_hits == 191
    assert primeiro.denies == 14
    assert primeiro.nivel == 18
    assert primeiro.funcao == "mid"
    assert primeiro.duracao_partida_segundos == 2097
    assert primeiro.id_tempo == 20260902


def test_dano_recebido_soma_o_dicionario(carregar_fixture):
    """damage_taken vem quebrado por fonte de dano; a coluna guarda o total."""
    participacoes, _ = parse_participacoes(carregar_fixture(PARTIDA_REAL))
    assert participacoes[0].dano_recebido == 936  # 91 + 704 + 141


def test_dano_recebido_aceita_inteiro(carregar_fixture):
    participacoes, _ = parse_participacoes(carregar_fixture("opendota_match_anonimo"))
    assert participacoes[0].dano_recebido == 5000


def test_pontos_objetivo_normaliza_torres_e_roshan(carregar_fixture):
    participacoes, _ = parse_participacoes(carregar_fixture(PARTIDA_REAL))
    # towers_killed=1 + roshan_kills=1
    assert participacoes[0].pontos_objetivo == 2


def test_metricas_extras_guardam_o_que_e_so_do_dota(carregar_fixture):
    participacoes, _ = parse_participacoes(carregar_fixture(PARTIDA_REAL))
    extras = participacoes[0].metricas_extras

    assert extras["lane_efficiency_pct"] == 78
    assert extras["net_worth"] == 16699
    assert extras["tower_damage"] == 4857
    # Nao vira coluna: LoL e Valorant nunca preencheriam.
    assert "hero_healing" in extras


def test_equipe_derivada_do_slot_quando_isradiant_falta(carregar_fixture):
    """isRadiant nem sempre vem; player_slot >= 128 e Dire."""
    participacoes, _ = parse_participacoes(carregar_fixture("opendota_match_anonimo"))

    assert participacoes[0].equipe == "radiant"  # slot 0
    assert participacoes[1].equipe == "dire"  # slot 128


def test_vitoria_derivada_de_radiant_win_quando_win_falta(carregar_fixture):
    participacoes, _ = parse_participacoes(carregar_fixture("opendota_match_anonimo"))

    # radiant_win = false
    assert participacoes[0].vitoria is False
    assert participacoes[1].vitoria is True


def test_jogador_anonimo_nao_entra_na_dimensao(carregar_fixture):
    """account_id nulo ou 0 e comum; o fato existe, a dimensao nao."""
    participacoes, jogadores = parse_participacoes(
        carregar_fixture("opendota_match_anonimo")
    )

    assert jogadores == []
    assert all(p.id_jogador_externo is None for p in participacoes)
    # O fato continua analisavel: KDA e heroi seguem preenchidos.
    assert participacoes[0].id_personagem_externo == "14"
    assert participacoes[0].kills == 3


def test_hero_id_zero_nao_vira_personagem(carregar_fixture):
    """hero_id 0 significa ausencia de heroi, nao o heroi de id 0."""
    participacoes, _ = parse_participacoes(carregar_fixture("opendota_match_anonimo"))
    assert participacoes[1].id_personagem_externo is None


def test_participacoes_de_payload_invalido():
    assert parse_participacoes(None) == ([], [])
    assert parse_participacoes({"match_id": 1}) == ([], [])


# --- helpers ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(1788368820, INICIO), (0, None), (None, None), ("abc", None)],
)
def test_epoch_para_datetime(valor, esperado):
    assert epoch_para_datetime(valor) == esperado


def test_chave_tempo():
    assert chave_tempo(INICIO) == 20260902
    assert chave_tempo(None) is None


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [(2, "captains mode"), (23, "turbo"), (999, "modo_999"), (None, None)],
)
def test_nome_do_modo(codigo, esperado):
    assert nome_do_modo(codigo) == esperado


# --- montagem completa -----------------------------------------------------


def test_transformar_consolida_a_coleta(carregar_fixture):
    registros = [
        _registro(ENDPOINT_HEROIS, "todos", carregar_fixture("opendota_heroes")),
        _registro(ENDPOINT_LISTA, "ultimas", [8979484553]),
        _registro(ENDPOINT_PARTIDA, "8979484553", carregar_fixture(PARTIDA_REAL)),
    ]

    resultado = transformar(registros)

    assert len(resultado.personagens) == 8
    assert len(resultado.partidas) == 1
    assert len(resultado.jogadores) == 10
    assert len(resultado.participacoes) == 10
    assert resultado.total == 29


def test_transformar_descarta_partida_sem_jogadores(carregar_fixture):
    registros = [
        _registro(
            ENDPOINT_PARTIDA,
            "8000000002",
            carregar_fixture("opendota_match_sem_jogadores"),
        )
    ]

    resultado = transformar(registros)
    assert resultado.partidas == []
    assert resultado.participacoes == []


def test_transformar_deduplica_a_mesma_partida(carregar_fixture):
    """O mesmo payload relido do disco duas vezes nao duplica o fato."""
    payload = carregar_fixture(PARTIDA_REAL)
    registros = [
        _registro(ENDPOINT_PARTIDA, "8979484553", payload),
        _registro(ENDPOINT_PARTIDA, "8979484553", payload),
    ]

    resultado = transformar(registros)
    assert len(resultado.partidas) == 1
    assert len(resultado.participacoes) == 10


def test_transformar_ignora_outras_fontes(carregar_fixture):
    registro = RawRecord(
        fonte="steam",
        endpoint="appdetails",
        identificador="570",
        payload={},
        coletado_em=INICIO,
    )
    assert transformar([registro]).total == 0
