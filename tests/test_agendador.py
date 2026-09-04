"""Testes do agendador de coleta.

Nao ha rede aqui, e nao ha coletor de verdade: o que se testa e o laco. As
tarefas sao funcoes falsas que retornam sucesso, retornam falha ou explodem -
os tres desfechos que a producao produz.

O que estes testes protegem e o comportamento que so apareceria as tres da
manha: uma fonte fora do ar levando as outras junto, um SIGTERM ignorado por
uma hora, ou uma falha reagendada para daqui a doze horas.
"""

from __future__ import annotations

import threading

import pytest

from agendador import (
    ESPERA_APOS_FALHA_SEGUNDOS,
    Parada,
    Tarefa,
    _executar,
    montar_tarefas,
)
from collectors.base import CollectionResult


def _tarefa(executar, intervalo: float = 600.0) -> Tarefa:
    return Tarefa(nome="fake", intervalo_segundos=intervalo, executar=executar)


def _ok(*_args) -> CollectionResult:
    return CollectionResult(
        fonte="fake", sucesso=True, registros_coletados=3, registros_carregados=3
    )


def _falha(*_args) -> CollectionResult:
    return CollectionResult(fonte="fake", sucesso=False, erro="a origem recusou")


def _explode(*_args) -> CollectionResult:
    raise ConnectionError("DNS nao resolveu")


# ---------------------------------------------------------------- execucao


def test_sucesso_conta_execucao():
    tarefa = _tarefa(_ok)
    assert _executar(tarefa, None, None) is True
    assert (tarefa.execucoes, tarefa.falhas) == (1, 0)


def test_excecao_do_coletor_nao_escapa():
    """Uma fonte fora do ar nao pode derrubar as outras duas.

    Se esta excecao subir, o laco morre e o container reinicia - e com
    `rodar_ao_iniciar` ele recomeca do zero, formando um ciclo de crash que
    martela a API que ja estava com problema.
    """
    tarefa = _tarefa(_explode)
    assert _executar(tarefa, None, None) is False
    assert tarefa.falhas == 1


def test_resultado_sem_sucesso_conta_falha():
    """O coletor pode devolver `sucesso=False` sem levantar nada.

    Tratar isso como sucesso reagendaria para o intervalo cheio, e uma fonte
    quebrada ficaria seis horas em silencio antes da proxima tentativa.
    """
    tarefa = _tarefa(_falha)
    assert _executar(tarefa, None, None) is False
    assert tarefa.falhas == 1
    assert tarefa.execucoes == 1


# -------------------------------------------------------------- reagendar


def test_sucesso_reagenda_no_intervalo_normal():
    tarefa = _tarefa(_ok, intervalo=3600.0)
    tarefa.reagendar(agora=1000.0, sucesso=True)
    assert tarefa.proxima_em == 1000.0 + 3600.0


def test_falha_reagenda_mais_cedo_que_o_intervalo():
    """Falhar nao pode empurrar a fonte para o fim da fila.

    Com intervalo de 12h (Liquipedia), reagendar a falha para o intervalo cheio
    significaria meio dia sem agenda por causa de um timeout de dez segundos.
    """
    tarefa = _tarefa(_falha, intervalo=43200.0)
    tarefa.reagendar(agora=1000.0, sucesso=False)

    assert tarefa.proxima_em == 1000.0 + ESPERA_APOS_FALHA_SEGUNDOS
    assert tarefa.proxima_em < 1000.0 + tarefa.intervalo_segundos


# ------------------------------------------------------------------ parada


def test_dormir_acorda_no_sinal():
    """SIGTERM tem de interromper a espera, nao esperar a hora acabar.

    `docker compose stop` da dez segundos antes do SIGKILL. Um `sleep(3600)`
    perderia esse prazo em toda reinicializacao.
    """
    parada = Parada()
    threading.Timer(0.05, parada.pedir_parada).start()

    assert parada.dormir(30.0) is True
    assert parada.parando is True


def test_dormir_devolve_falso_quando_so_o_tempo_passa():
    parada = Parada()
    assert parada.dormir(0.01) is False
    assert parada.parando is False


def test_parada_e_idempotente():
    parada = Parada()
    parada.pedir_parada()
    parada.pedir_parada()
    assert parada.parando is True


# ------------------------------------------------------------- montagem


def test_intervalos_vem_da_configuracao():
    """Os intervalos sao configuraveis por `.env`, nao constantes no codigo."""

    class FakeSettings:
        agendador_steam_minutos = 15
        agendador_opendota_minutos = 30
        agendador_liquipedia_minutos = 45
        agendador_equipes_minutos = 60
        agendador_brackets_minutos = 75
        agendador_ranking_minutos = 90
        agendador_precos_minutos = 120
        agendador_opendota_limite = 10
        agendador_tempo_jogo_minutos = 150
        itad_api_key = "chave-de-teste"
        hltb_enabled = True

    tarefas = {t.nome: t.intervalo_segundos for t in montar_tarefas(FakeSettings())}
    assert tarefas == {
        "steam": 900,
        "opendota": 1800,
        "liquipedia": 2700,
        "equipes": 3600,
        "brackets": 4500,
        "ranking": 5400,
        "precos": 7200,
        "tempo_jogo": 9000,
    }


def test_tarefa_de_preco_so_entra_com_chave_do_itad():
    class SemChave:
        agendador_steam_minutos = 60
        agendador_opendota_minutos = 360
        agendador_liquipedia_minutos = 720
        agendador_equipes_minutos = 1440
        agendador_brackets_minutos = 1440
        agendador_ranking_minutos = 10080
        agendador_precos_minutos = 720
        agendador_opendota_limite = 100
        agendador_tempo_jogo_minutos = 1440
        itad_api_key = None
        hltb_enabled = True

    nomes = {t.nome for t in montar_tarefas(SemChave())}
    assert "precos" not in nomes


def test_tarefa_de_tempo_jogo_nao_entra_quando_desabilitada():
    class Desabilitada:
        agendador_steam_minutos = 60
        agendador_opendota_minutos = 360
        agendador_liquipedia_minutos = 720
        agendador_equipes_minutos = 1440
        agendador_brackets_minutos = 1440
        agendador_ranking_minutos = 10080
        agendador_precos_minutos = 720
        agendador_opendota_limite = 100
        agendador_tempo_jogo_minutos = 1440
        itad_api_key = None
        hltb_enabled = False

    nomes = {t.nome for t in montar_tarefas(Desabilitada())}
    assert "tempo_jogo" not in nomes


@pytest.mark.parametrize(
    "fonte",
    ["steam", "opendota", "liquipedia", "equipes", "brackets", "ranking", "tempo_jogo"],
)
def test_as_tres_fontes_estao_agendadas(fonte: str):
    from config import get_settings

    nomes = {t.nome for t in montar_tarefas(get_settings())}
    assert fonte in nomes


def test_a_proxima_tarefa_e_a_de_menor_prazo():
    """O laco escolhe por `proxima_em`, nao pela ordem da lista.

    Sem isso, a Steam (60 min) so rodaria depois da Liquipedia (720 min) por
    estar antes na lista, e o intervalo configurado nao significaria nada.
    """
    steam = Tarefa("steam", 3600, _ok, proxima_em=100.0)
    liquipedia = Tarefa("liquipedia", 43200, _ok, proxima_em=50.0)
    opendota = Tarefa("opendota", 21600, _ok, proxima_em=200.0)

    escolhida = min([steam, liquipedia, opendota], key=lambda t: t.proxima_em)
    assert escolhida.nome == "liquipedia"
