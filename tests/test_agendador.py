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

from config import get_settings
from agendador import (
    ESPERA_APOS_FALHA_SEGUNDOS,
    Parada,
    Tarefa,
    _conferir_duracao,
    _executar,
    montar_tarefas,
)
from services.collectors.base import CollectionResult


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
        agendador_steam_online_minutos = 15
        agendador_steam_ofertas_minutos = 15
        steam_api_key = None
        agendador_agenda_proxima_minutos = 5
        agendador_opendota_minutos = 30
        agendador_liquipedia_minutos = 45
        agendador_equipes_minutos = 60
        agendador_brackets_minutos = 75
        agendador_ranking_minutos = 90
        agendador_precos_minutos = 120
        agendador_opendota_limite = 10
        agendador_tempo_jogo_minutos = 150
        agendador_agentes_minutos = 10080
        agendador_esports_opgg_minutos = 360
        agendador_vlr_minutos = 1440
        agendador_vlr_rankings_minutos = 10080
        agendador_ubi_r6_minutos = 10080
        agendador_owcs_minutos = 1440
        agendador_rlcs_minutos = 1440
        agendador_dltv_minutos = 1440
        agendador_vlr_detalhes_minutos = 1440
        agendador_lolesports_minutos = 1440
        agendador_lolesports_cenario_minutos = 720
        agendador_treino_confronto_minutos = 480
        agendador_pandascore_minutos = 30
        agendador_xbox_minutos = 180
        agendador_resumo_reviews_minutos = 200
        opgg_enabled = True
        itad_api_key = "chave-de-teste"
        groq_api_key = "chave-groq-teste"
        pandascore_api_key = None
        liquipedia_enabled = True
        hltb_enabled = True
        xbox_enabled = True

    tarefas = {t.nome: t.intervalo_segundos for t in montar_tarefas(FakeSettings())}
    assert tarefas == {
        "steam": 900,
        "steam_online": 900,
        "steam_ofertas": 900,
        "vlr_agenda": 300,
        "hltv": 300,
        "opendota": 1800,
        "liquipedia": 2700,
        "equipes": 3600,
        "brackets": 4500,
        "ranking": 5400,
        "precos": 7200,
        "resumo_reviews": 12000,
        "tempo_jogo": 9000,
        "xbox": 10800,
        "esports_opgg": 21600,
        "vlr": 86400,
        "vlr_rankings": 604800,
        "ubi_r6": 604800,
        "owcs": 86400,
        "rlcs": 86400,
        "dltv": 86400,
        "vlr_detalhes": 86400,
        "lolesports": 86400,
        "lol_cenario": 43200,
        "treino_confronto": 28800,
        "agentes_valorant": 604800,
        "campeoes_lol": 604800,
        "herois_dota": 604800,
    }


def test_tarefa_de_preco_so_entra_com_chave_do_itad():
    class SemChave:
        agendador_steam_minutos = 60
        agendador_steam_online_minutos = 15
        agendador_steam_ofertas_minutos = 15
        steam_api_key = None
        agendador_agenda_proxima_minutos = 5
        agendador_opendota_minutos = 360
        agendador_liquipedia_minutos = 720
        agendador_equipes_minutos = 1440
        agendador_brackets_minutos = 1440
        agendador_ranking_minutos = 10080
        agendador_precos_minutos = 720
        agendador_opendota_limite = 100
        agendador_tempo_jogo_minutos = 1440
        agendador_agentes_minutos = 10080
        agendador_esports_opgg_minutos = 360
        agendador_vlr_minutos = 1440
        agendador_vlr_rankings_minutos = 10080
        agendador_ubi_r6_minutos = 10080
        agendador_owcs_minutos = 1440
        agendador_rlcs_minutos = 1440
        agendador_dltv_minutos = 1440
        agendador_vlr_detalhes_minutos = 1440
        agendador_lolesports_minutos = 1440
        agendador_lolesports_cenario_minutos = 720
        agendador_treino_confronto_minutos = 480
        agendador_pandascore_minutos = 30
        opgg_enabled = True
        itad_api_key = None
        groq_api_key = None
        pandascore_api_key = None
        liquipedia_enabled = True
        hltb_enabled = True
        xbox_enabled = False
        agendador_xbox_minutos = 360

    nomes = {t.nome for t in montar_tarefas(SemChave())}
    assert "precos" not in nomes


def test_tarefa_de_resumo_reviews_so_entra_com_chave_do_groq():
    class SemChave:
        agendador_steam_minutos = 60
        agendador_steam_online_minutos = 15
        agendador_steam_ofertas_minutos = 15
        steam_api_key = None
        agendador_agenda_proxima_minutos = 5
        agendador_opendota_minutos = 360
        agendador_liquipedia_minutos = 720
        agendador_equipes_minutos = 1440
        agendador_brackets_minutos = 1440
        agendador_ranking_minutos = 10080
        agendador_precos_minutos = 720
        agendador_opendota_limite = 100
        agendador_tempo_jogo_minutos = 1440
        agendador_agentes_minutos = 10080
        agendador_esports_opgg_minutos = 360
        agendador_vlr_minutos = 1440
        agendador_vlr_rankings_minutos = 10080
        agendador_ubi_r6_minutos = 10080
        agendador_owcs_minutos = 1440
        agendador_rlcs_minutos = 1440
        agendador_dltv_minutos = 1440
        agendador_vlr_detalhes_minutos = 1440
        agendador_lolesports_minutos = 1440
        agendador_lolesports_cenario_minutos = 720
        agendador_treino_confronto_minutos = 480
        agendador_pandascore_minutos = 30
        opgg_enabled = True
        itad_api_key = None
        groq_api_key = None
        pandascore_api_key = None
        liquipedia_enabled = True
        hltb_enabled = True
        xbox_enabled = False
        agendador_xbox_minutos = 360

    nomes = {t.nome for t in montar_tarefas(SemChave())}
    assert "resumo_reviews" not in nomes


def test_tarefa_de_tempo_jogo_nao_entra_quando_desabilitada():
    class Desabilitada:
        agendador_steam_minutos = 60
        agendador_steam_online_minutos = 15
        agendador_steam_ofertas_minutos = 15
        steam_api_key = None
        agendador_agenda_proxima_minutos = 5
        agendador_opendota_minutos = 360
        agendador_liquipedia_minutos = 720
        agendador_equipes_minutos = 1440
        agendador_brackets_minutos = 1440
        agendador_ranking_minutos = 10080
        agendador_precos_minutos = 720
        agendador_opendota_limite = 100
        agendador_tempo_jogo_minutos = 1440
        agendador_agentes_minutos = 10080
        agendador_esports_opgg_minutos = 360
        agendador_vlr_minutos = 1440
        agendador_vlr_rankings_minutos = 10080
        agendador_ubi_r6_minutos = 10080
        agendador_owcs_minutos = 1440
        agendador_rlcs_minutos = 1440
        agendador_dltv_minutos = 1440
        agendador_vlr_detalhes_minutos = 1440
        agendador_lolesports_minutos = 1440
        agendador_lolesports_cenario_minutos = 720
        agendador_treino_confronto_minutos = 480
        agendador_pandascore_minutos = 30
        opgg_enabled = True
        itad_api_key = None
        groq_api_key = None
        pandascore_api_key = None
        liquipedia_enabled = True
        hltb_enabled = False
        xbox_enabled = False
        agendador_xbox_minutos = 360

    nomes = {t.nome for t in montar_tarefas(Desabilitada())}
    assert "tempo_jogo" not in nomes


def test_tarefa_de_xbox_nao_entra_quando_desabilitada():
    class Desabilitada:
        agendador_steam_minutos = 60
        agendador_steam_online_minutos = 15
        agendador_steam_ofertas_minutos = 15
        steam_api_key = None
        agendador_agenda_proxima_minutos = 5
        agendador_opendota_minutos = 360
        agendador_liquipedia_minutos = 720
        agendador_equipes_minutos = 1440
        agendador_brackets_minutos = 1440
        agendador_ranking_minutos = 10080
        agendador_precos_minutos = 720
        agendador_opendota_limite = 100
        agendador_tempo_jogo_minutos = 1440
        agendador_agentes_minutos = 10080
        agendador_esports_opgg_minutos = 360
        agendador_vlr_minutos = 1440
        agendador_vlr_rankings_minutos = 10080
        agendador_ubi_r6_minutos = 10080
        agendador_owcs_minutos = 1440
        agendador_rlcs_minutos = 1440
        agendador_dltv_minutos = 1440
        agendador_vlr_detalhes_minutos = 1440
        agendador_lolesports_minutos = 1440
        agendador_lolesports_cenario_minutos = 720
        agendador_treino_confronto_minutos = 480
        agendador_pandascore_minutos = 30
        agendador_xbox_minutos = 360
        opgg_enabled = True
        itad_api_key = None
        groq_api_key = None
        pandascore_api_key = None
        liquipedia_enabled = True
        hltb_enabled = True
        xbox_enabled = False

    nomes = {t.nome for t in montar_tarefas(Desabilitada())}
    assert "xbox" not in nomes


def test_tarefa_de_catalogo_steam_so_entra_com_chave(monkeypatch):
    """`steam_catalogo` (Fase 35) precisa de STEAM_API_KEY - sem ela o
    `GetAppList` nem aceita a chamada (ver `SteamStoreClient.listar_apps`)."""

    class SemChave:
        agendador_steam_minutos = 60
        agendador_steam_online_minutos = 15
        agendador_steam_ofertas_minutos = 15
        steam_api_key = None
        agendador_steam_catalogo_minutos = 20
        agendador_steam_precos_alterados_minutos = 10
        agendador_agenda_proxima_minutos = 5
        agendador_opendota_minutos = 360
        agendador_liquipedia_minutos = 720
        agendador_equipes_minutos = 1440
        agendador_brackets_minutos = 1440
        agendador_ranking_minutos = 10080
        agendador_precos_minutos = 720
        agendador_opendota_limite = 100
        agendador_tempo_jogo_minutos = 1440
        agendador_agentes_minutos = 10080
        agendador_esports_opgg_minutos = 360
        agendador_vlr_minutos = 1440
        agendador_vlr_rankings_minutos = 10080
        agendador_ubi_r6_minutos = 10080
        agendador_owcs_minutos = 1440
        agendador_rlcs_minutos = 1440
        agendador_dltv_minutos = 1440
        agendador_vlr_detalhes_minutos = 1440
        agendador_lolesports_minutos = 1440
        agendador_lolesports_cenario_minutos = 720
        agendador_treino_confronto_minutos = 480
        agendador_pandascore_minutos = 30
        agendador_xbox_minutos = 360
        opgg_enabled = True
        itad_api_key = None
        groq_api_key = None
        pandascore_api_key = None
        liquipedia_enabled = True
        hltb_enabled = True
        xbox_enabled = False

    nomes = {t.nome for t in montar_tarefas(SemChave())}
    assert "steam_catalogo" not in nomes
    assert "steam_precos_alterados" not in nomes

    class ComChave(SemChave):
        steam_api_key = "chave-de-teste"

    tarefas = {t.nome: t.intervalo_segundos for t in montar_tarefas(ComChave())}
    assert tarefas.get("steam_catalogo") == 20 * 60
    assert tarefas.get("steam_precos_alterados") == 10 * 60


def test_pandascore_troca_o_hltv_quando_ha_chave():
    class ComPandaScore:
        agendador_steam_minutos = 60
        agendador_steam_online_minutos = 15
        agendador_steam_ofertas_minutos = 15
        steam_api_key = None
        agendador_agenda_proxima_minutos = 5
        agendador_opendota_minutos = 360
        agendador_liquipedia_minutos = 720
        agendador_equipes_minutos = 1440
        agendador_brackets_minutos = 1440
        agendador_ranking_minutos = 10080
        agendador_precos_minutos = 720
        agendador_opendota_limite = 100
        agendador_tempo_jogo_minutos = 1440
        agendador_agentes_minutos = 10080
        agendador_esports_opgg_minutos = 360
        agendador_vlr_minutos = 1440
        agendador_vlr_rankings_minutos = 10080
        agendador_ubi_r6_minutos = 10080
        agendador_owcs_minutos = 1440
        agendador_rlcs_minutos = 1440
        agendador_dltv_minutos = 1440
        agendador_vlr_detalhes_minutos = 1440
        agendador_lolesports_minutos = 1440
        agendador_lolesports_cenario_minutos = 720
        agendador_treino_confronto_minutos = 480
        agendador_pandascore_minutos = 30
        opgg_enabled = True
        itad_api_key = None
        groq_api_key = None
        pandascore_api_key = "chave-de-teste"
        liquipedia_enabled = True
        hltb_enabled = True
        xbox_enabled = False
        agendador_xbox_minutos = 360

    tarefas = {t.nome: t.intervalo_segundos for t in montar_tarefas(ComPandaScore())}
    for nome in ("pandascore_cs", "pandascore_lol", "pandascore_cod",
                 "pandascore_ow", "pandascore_r6", "pandascore_rl",
                 "pandascore_val"):
        assert tarefas.get(nome) == 1800
    assert "hltv" not in tarefas
    # LoL da PandaScore roda JUNTO do OP.GG (fontes complementares).
    assert "esports_opgg" in tarefas


@pytest.mark.parametrize(
    "fonte",
    ["steam", "opendota", "liquipedia", "equipes", "brackets", "ranking",
     "tempo_jogo", "lolesports", "lol_cenario"],
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


# --- A tarefa cabe no proprio intervalo? -------------------------------------
#
# O bug de 2026-09-16: a tarefa `steam` levava 16,7 horas por passada numa
# agenda de 60 minutos, e o log nao dizia nada - cada app era um INFO de
# sucesso. O agendador ja media a duracao e ja sabia o intervalo; so nunca
# comparava os dois. Estes testes fixam a comparacao.


def _tarefa_de(intervalo: float) -> Tarefa:
    return Tarefa(nome="fake", intervalo_segundos=intervalo, executar=_ok)


def test_estourar_o_intervalo_e_erro(caplog):
    """O caso real: 16,7h de trabalho num slot de 1h."""
    with caplog.at_level("ERROR"):
        _conferir_duracao(_tarefa_de(3600), 60_000)
    assert "nao cabe no proprio intervalo" in caplog.text


def test_ocupar_metade_do_intervalo_ja_avisa(caplog):
    """Ainda funciona, mas sem folga - e toda fila aqui cresce com o
    catalogo. O aviso e pra dar tempo de reagir antes de virar erro."""
    with caplog.at_level("WARNING"):
        _conferir_duracao(_tarefa_de(3600), 1900)
    assert "boa parte do proprio intervalo" in caplog.text


def test_tarefa_folgada_nao_reclama(caplog):
    """O caso normal depois da correcao: a coleta Steam leva ~6min de 60.
    Se isto virasse ruido, o log deixaria de servir pra achar o problema."""
    with caplog.at_level("WARNING"):
        _conferir_duracao(_tarefa_de(3600), 378)
    assert caplog.text == ""


def test_duracao_e_conferida_mesmo_quando_a_tarefa_explode(caplog):
    """Estourar o intervalo E falhar e o pior caso dos dois - e era
    justamente o que nao deixava numero nenhum no log."""

    def _demorada_e_quebrada(*_args):
        raise RuntimeError("a origem caiu")

    tarefa = Tarefa(
        nome="fake", intervalo_segundos=0.0001, executar=_demorada_e_quebrada
    )
    with caplog.at_level("ERROR"):
        assert _executar(tarefa, None, None) is False
    assert "nao cabe no proprio intervalo" in caplog.text


# --- Vigia de tarefa travada --------------------------------------------------
#
# `_conferir_duracao` so mede tarefa que TERMINA, e por isso nao viu o pior
# caso real: 8 horas parado em `hrtimer_nanosleep` (429 do ITAD com
# `Retry-After` longo), CPU em 0% e nenhuma linha de log. Estes testes fixam
# o vigia que passa a gritar nesse caso.


def test_vigia_avisa_quando_a_tarefa_passa_do_limite(caplog, monkeypatch):
    from agendador import _FATOR_TRAVADA, _Vigia

    vigia = _Vigia()
    tarefa = Tarefa(nome="itad", intervalo_segundos=60.0, executar=_ok)

    relogio = {"agora": 1000.0}
    monkeypatch.setattr("agendador.time.monotonic", lambda: relogio["agora"])

    vigia.entrando(tarefa)
    # Ainda dentro do limite: silencio.
    relogio["agora"] += 60.0 * _FATOR_TRAVADA - 1
    with caplog.at_level("ERROR"):
        vigia.conferir()
    assert caplog.text == ""

    relogio["agora"] += 2
    with caplog.at_level("ERROR"):
        vigia.conferir()
    assert "possivelmente travada" in caplog.text
    # O nome da tarefa vai em `extra=`, que o `caplog.text` nao renderiza -
    # e o campo estruturado que o log JSON de producao publica.
    assert caplog.records[-1].fonte == "itad"
    assert caplog.records[-1].segundos >= 180


def test_vigia_avisa_uma_vez_so_por_execucao(caplog, monkeypatch):
    """O vigia acorda de minuto em minuto; sem isto, uma tarefa travada por
    8h encheria o log com 480 linhas iguais e esconderia o resto."""
    from agendador import _Vigia

    vigia = _Vigia()
    relogio = {"agora": 1000.0}
    monkeypatch.setattr("agendador.time.monotonic", lambda: relogio["agora"])

    vigia.entrando(Tarefa(nome="itad", intervalo_segundos=60.0, executar=_ok))
    relogio["agora"] += 10_000

    with caplog.at_level("ERROR"):
        vigia.conferir()
        vigia.conferir()
        vigia.conferir()
    assert caplog.text.count("possivelmente travada") == 1


def test_vigia_calado_sem_tarefa_em_execucao(caplog):
    from agendador import _Vigia

    vigia = _Vigia()
    with caplog.at_level("ERROR"):
        vigia.conferir()
    assert caplog.text == ""

    vigia.entrando(Tarefa(nome="x", intervalo_segundos=60.0, executar=_ok))
    vigia.saindo()
    with caplog.at_level("ERROR"):
        vigia.conferir()
    assert caplog.text == ""


# --- Scraping da Liquipedia pode ser desligado --------------------------------


def _nomes(desligada: bool) -> set[str]:
    settings = get_settings().model_copy(update={"liquipedia_enabled": not desligada})
    return {t.nome for t in montar_tarefas(settings)}


def test_liquipedia_ligada_agenda_as_quatro_tarefas():
    assert {"liquipedia", "equipes", "brackets", "owcs"} <= _nomes(desligada=False)


def test_liquipedia_desligada_tira_as_quatro():
    """As quatro saem JUNTAS porque falham juntas: a trava de 429 da
    Liquipedia e por IP, entao bloquear uma bloqueia todas. Medido em
    producao (2026-09-17): 65 falhas numa hora entre as quatro, com o `owcs`
    em 136 seguidas."""
    nomes = _nomes(desligada=True)
    assert {"liquipedia", "equipes", "brackets", "owcs"} & nomes == set()


def test_desligar_liquipedia_nao_afeta_as_outras_fontes():
    """O resto do agendador nao pode ir junto - as fontes que cobrem o mesmo
    dominio (PandaScore, vlr, Valve) seguem valendo."""
    ligada, desligada = _nomes(desligada=False), _nomes(desligada=True)
    perdidas = ligada - desligada
    assert perdidas == {"liquipedia", "equipes", "brackets", "owcs"}
