"""Avisos operacionais por Telegram.

O que estes testes protegem nao e "a mensagem chega" - isso depende do
Telegram e de alguem ter dado `/start` no bot. E o que fica entre o problema
e o aviso:

* **o canal nunca derruba quem avisa** - uma coleta nao pode falhar porque a
  notificacao falhou. Foi a licao de 2026-09-16, quando uma chamada HTTP
  dentro do agendador dormiu 8 horas;
* **cooldown** - a Liquipedia deste projeto falha a cada ciclo ha 13 dias.
  Sem cooldown o chat receberia uma mensagem por ciclo, seria silenciado em
  uma semana, e o canal inteiro deixaria de servir. Fadiga de alerta e o
  modo de falha real aqui, nao a falta de cobertura;
* **sequencia antes de aviso** - fonte externa pisca; uma falha isolada nao
  e evento.
"""

from __future__ import annotations

import time

import pytest

from agendador import (
    _FALHAS_ANTES_DE_AVISAR,
    Tarefa,
    _contar_falha,
    montar_resumo,
)
from services.collectors.base import CollectionResult
from services.notificacoes import telegram


def _ok(*_args) -> CollectionResult:
    return CollectionResult(fonte="fake", sucesso=True)


@pytest.fixture(autouse=True)
def cooldown_limpo():
    telegram.limpar_cooldowns()
    yield
    telegram.limpar_cooldowns()


# --- O canal em si -----------------------------------------------------------


def test_sem_configuracao_nao_envia_e_nao_quebra(monkeypatch):
    """Sem token/chat o canal e um no-op silencioso - mesmo padrao das outras
    chaves do projeto, em que a ausencia da configuracao E o desligado."""
    from config import get_settings

    settings = get_settings().model_copy(
        update={"telegram_bot_token": None, "telegram_chat_id": None}
    )
    monkeypatch.setattr(telegram, "get_settings", lambda: settings)

    assert telegram.configurado() is False
    assert telegram.enviar("qualquer coisa") is False


def test_falha_de_rede_nao_levanta(monkeypatch):
    """O teste mais importante do arquivo: avisar sobre um problema nao pode
    causar outro. Se o Telegram estiver fora do ar, a coleta segue."""
    from config import get_settings

    settings = get_settings().model_copy(
        update={"telegram_bot_token": "t", "telegram_chat_id": "1"}
    )
    monkeypatch.setattr(telegram, "get_settings", lambda: settings)

    def explode(*_a, **_k):
        raise ConnectionError("telegram fora do ar")

    monkeypatch.setattr(telegram.requests, "post", explode)
    assert telegram.enviar("aviso") is False  # devolve False, nao levanta


def test_status_diferente_de_200_nao_levanta(monkeypatch):
    from config import get_settings

    settings = get_settings().model_copy(
        update={"telegram_bot_token": "t", "telegram_chat_id": "1"}
    )
    monkeypatch.setattr(telegram, "get_settings", lambda: settings)

    class Resposta:
        status_code = 400
        text = '{"ok":false,"description":"Bad Request: chat not found"}'

    monkeypatch.setattr(telegram.requests, "post", lambda *a, **k: Resposta())
    assert telegram.enviar("aviso") is False


def test_cooldown_segura_a_repeticao(monkeypatch):
    from config import get_settings

    settings = get_settings().model_copy(
        update={"telegram_bot_token": "t", "telegram_chat_id": "1"}
    )
    monkeypatch.setattr(telegram, "get_settings", lambda: settings)

    enviados: list[str] = []

    class Resposta:
        status_code = 200
        text = "{}"

    def post(_url, data=None, **_k):
        enviados.append(data["text"])
        return Resposta()

    monkeypatch.setattr(telegram.requests, "post", post)

    assert telegram.enviar("primeiro", chave="x", cooldown_segundos=3600) is True
    assert telegram.enviar("segundo", chave="x", cooldown_segundos=3600) is False
    assert enviados == ["primeiro"]

    # Chave diferente passa - o cooldown e por tipo de evento, nao global.
    assert telegram.enviar("outro", chave="y", cooldown_segundos=3600) is True


def test_sem_chave_envia_sempre(monkeypatch):
    """O resumo diario nao usa chave: ele e raro por natureza, e suprimi-lo
    por cooldown seria perder justamente a prova de que o canal esta vivo."""
    from config import get_settings

    settings = get_settings().model_copy(
        update={"telegram_bot_token": "t", "telegram_chat_id": "1"}
    )
    monkeypatch.setattr(telegram, "get_settings", lambda: settings)

    class Resposta:
        status_code = 200
        text = "{}"

    monkeypatch.setattr(telegram.requests, "post", lambda *a, **k: Resposta())
    assert telegram.enviar("a") is True
    assert telegram.enviar("b") is True


# --- Quando o agendador decide avisar ----------------------------------------


def test_uma_falha_isolada_nao_avisa(monkeypatch):
    """Fonte externa pisca. Avisar na primeira faria o chat virar ruido."""
    avisos: list[str] = []
    monkeypatch.setattr(
        "agendador._avisar", lambda texto, chave, cooldown=3600.0: avisos.append(chave)
    )

    tarefa = Tarefa(nome="itad", intervalo_segundos=3600.0, executar=_ok)
    _contar_falha(tarefa, "timeout")

    assert tarefa.falhas_seguidas == 1
    assert avisos == []


def test_sequencia_de_falhas_avisa(monkeypatch):
    avisos: list[str] = []
    monkeypatch.setattr(
        "agendador._avisar", lambda texto, chave, cooldown=3600.0: avisos.append(chave)
    )

    tarefa = Tarefa(nome="itad", intervalo_segundos=3600.0, executar=_ok)
    for _ in range(_FALHAS_ANTES_DE_AVISAR):
        _contar_falha(tarefa, "timeout")

    assert avisos == ["falha:itad"]


# --- Resumo ------------------------------------------------------------------


def test_resumo_diz_quando_esta_tudo_bem():
    """Um canal que so fala quando ha problema e indistinguivel de um canal
    quebrado - por isso o resumo sai mesmo sem nada errado."""
    tarefas = [Tarefa(nome="steam", intervalo_segundos=3600.0, executar=_ok)]
    tarefas[0].execucoes = 5
    # Relogio real: `ultimo_sucesso` e comparado com `time.monotonic()`, entao
    # um valor fixo pequeno pareceria antiguissimo e cairia em "sem sucesso ha
    # tempo demais" - foi o que este teste pegou na primeira escrita.
    tarefas[0].ultimo_sucesso = time.monotonic()

    texto = montar_resumo(tarefas)
    assert "resumo de 24h" in texto
    assert "tudo dentro do esperado" in texto


def test_resumo_lista_o_que_esta_quebrado():
    quebrada = Tarefa(nome="itad", intervalo_segundos=3600.0, executar=_ok)
    quebrada.falhas_seguidas = _FALHAS_ANTES_DE_AVISAR
    quebrada.falhas = 4
    quebrada.execucoes = 4

    saudavel = Tarefa(nome="steam", intervalo_segundos=3600.0, executar=_ok)
    saudavel.execucoes = 10
    saudavel.ultimo_sucesso = time.monotonic()

    texto = montar_resumo([quebrada, saudavel])
    assert "falhando agora" in texto
    assert "itad" in texto
    assert "tudo dentro do esperado" not in texto


def test_resumo_nao_acusa_tarefa_que_nunca_rodou():
    """Tarefa que ainda nao teve a vez (`execucoes == 0`) nao e problema -
    acusa-la faria toda subida do agendador parecer incidente."""
    nova = Tarefa(nome="rlcs", intervalo_segundos=86400.0, executar=_ok)

    texto = montar_resumo([nova])
    assert "nunca tiveram sucesso" not in texto
    assert "tudo dentro do esperado" in texto
