"""Testes do parser da agenda e da reconciliacao de nomes de equipe.

A fixture sao dois blocos reais da pagina `Liquipedia:Matches`. Ela funciona
como contrato com o markup: este e o unico ponto do projeto que le HTML, e HTML
de wiki muda sem aviso. Se a Liquipedia renomear `match-info-header-opponent`,
o parser passa a devolver lista vazia - e sem estes testes isso apareceria
como "nenhum confronto agendado" na tela, que parece um fim de semana sem
jogos e nao um parser quebrado.
"""

from __future__ import annotations

from datetime import timezone

import pytest

from etl.load_liquipedia import _sem_enfeites, normalizar
from etl.transform_liquipedia import parse_agenda, transformar


@pytest.fixture(scope="module")
def payload(carregar_fixture):
    return carregar_fixture("liquipedia_matches")


@pytest.fixture(scope="module")
def agenda(payload):
    return transformar(payload).partidas


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_extrai_os_confrontos_da_pagina(agenda):
    assert len(agenda) == 2
    assert [(p.equipe_a_nome, p.equipe_b_nome) for p in agenda] == [
        ("PuckChamp", "Team Spirit Academy"),
        ("Pipsqueak+4", "DYNASTY (stack)"),
    ]


def test_usa_o_nome_canonico_e_nao_a_abreviacao(agenda):
    """O texto visivel e "SpiritAc"; o `title` do link e o nome de verdade."""
    assert "Team Spirit Academy" in {p.equipe_b_nome for p in agenda}
    assert "SpiritAc" not in {p.equipe_b_nome for p in agenda}


def test_horario_vira_datetime_em_utc(agenda):
    for partida in agenda:
        assert partida.inicio_previsto.tzinfo == timezone.utc


def test_formato_e_torneio_sao_extraidos(agenda):
    assert {p.formato for p in agenda} == {"Bo3"}
    assert {p.torneio for p in agenda} == {"EPL/Masters/2"}


def test_torneio_perde_a_ancora_de_dia(agenda):
    """O `title` vem como "EPL/Masters/2#September 3" - a âncora não é o nome."""
    assert all("#" not in (p.torneio or "") for p in agenda)


def test_id_externo_e_estavel_entre_execucoes(payload):
    """Sem chave estavel, cada coleta duplicaria a agenda inteira."""
    primeira = {p.id_externo for p in transformar(payload).partidas}
    segunda = {p.id_externo for p in transformar(payload).partidas}
    assert primeira == segunda
    assert len(primeira) == 2


def test_html_sem_confronto_devolve_lista_vazia():
    assert parse_agenda("") == []
    assert parse_agenda("<div>nada aqui</div>") == []


def test_payload_de_erro_da_api_nao_levanta():
    assert transformar({"error": {"code": "missingtitle"}}).total == 0
    assert transformar(None).total == 0
    assert transformar({"parse": {}}).total == 0


def test_confronto_sem_horario_definido_e_descartado():
    """A Liquipedia usa timestamp 0 para "a definir" - nao da para agendar."""
    html = (
        '<div class="match-info"><span data-timestamp="0"></span>'
        '<div class="match-info-header-opponent"><a title="A"></a></div>'
        '<div class="match-info-header-opponent"><a title="B"></a></div></div>'
    )
    assert parse_agenda(html) == []


def test_confronto_com_lado_indefinido_e_descartado():
    """"TBD" e chave ainda nao resolvida, nao um time."""
    html = (
        '<div class="match-info"><span data-timestamp="1788436800"></span>'
        '<div class="match-info-header-opponent"><a title="PuckChamp"></a></div>'
        '<div class="match-info-header-opponent"><a title="TBD"></a></div></div>'
    )
    assert parse_agenda(html) == []


# ---------------------------------------------------------------------------
# Reconciliacao
# ---------------------------------------------------------------------------


def test_normalizacao_junta_variacoes_de_pontuacao():
    """O caso real: a OpenDota cadastrou "_PowerRangers"; a wiki escreve outro."""
    assert normalizar("_PowerRangers") == normalizar("Power Rangers")
    assert normalizar("Pipsqueak+4") == normalizar("Pipsqueak + 4")
    assert normalizar("Água Time") == normalizar("agua-time")


def test_normalizacao_nao_junta_times_diferentes():
    assert normalizar("Team Spirit") != normalizar("Team Spirit Academy")
    assert normalizar("Nemiga Gaming") != normalizar("Team Nemesis")


def test_parenteses_de_desambiguacao_saem_do_nome():
    """"(stack)" e metadado de pagina da wiki, nao parte do nome do time."""
    assert _sem_enfeites("DYNASTY (stack)") == normalizar("DYNASTY")
    assert _sem_enfeites("Crescent (Chinese team)") == normalizar("Crescent")


def test_sufixo_de_organizacao_sai_do_nome():
    assert _sem_enfeites("Direborn Esports") == normalizar("DIREBORN")
    assert _sem_enfeites("Nemiga Gaming") == normalizar("Nemiga")


def test_sufixo_nao_e_removido_quando_sobraria_quase_nada():
    """Sem o piso de tamanho, um time chamado "Esports" viraria string vazia."""
    assert _sem_enfeites("Esports") == "esports"
    assert _sem_enfeites("Team") == "team"
