"""Avisos operacionais por Telegram.

**O que este canal cobre, e o que nao.** O Netdata da VPS ja manda alarme de
infraestrutura (CPU, RAM, disco, load, container caindo) direto pro mesmo
chat, sem passar por aqui - sao 61 alarmes prontos. O que ele nao sabe e o
que so o PlayDB conhece: que uma tarefa de coleta travou segurando a fila,
que uma fonte parou de entregar dado, que a sincronizacao da Steam falhou.
E isso que este modulo manda.

**Tres decisoes que vieram de erro real.**

1. *Timeout curto e sem retry.* Em 2026-09-16 o agendador ficou 8 horas
   parado porque uma chamada HTTP dormiu dentro de um retry (`Retry-After`
   sem teto). Avisar sobre um problema nao pode causar outro: este modulo
   usa `requests` direto, com timeout de poucos segundos e ZERO tentativas -
   nunca o `RateLimitedClient`, que tem backoff e pode dormir.

2. *Nunca levanta.* Um aviso que quebra a coleta e pior que aviso nenhum.
   Toda falha aqui vira log e segue.

3. *Cooldown por chave.* Uma tarefa que falha a cada 12 horas (a Liquipedia
   vive assim, por 429) mandaria uma mensagem por ciclo pra sempre. Depois
   de uma semana o chat estaria silenciado, e ai o canal inteiro nao serve
   mais - fadiga de alerta e o modo de falha real deste tipo de
   integracao, nao a falta de cobertura.

Sem `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no `.env`, `enviar()` nao faz
nada e devolve `False` - mesmo padrao das outras chaves do projeto, em que a
ausencia da configuracao E o "desligado".
"""

from __future__ import annotations

import logging
import threading
import time

import requests

from config import get_settings

logger = logging.getLogger(__name__)

_URL = "https://api.telegram.org/bot{token}/sendMessage"

#: Timeout total da chamada. Curto de proposito: o agendador roda as tarefas
#: em serie, entao qualquer espera aqui atrasa a coleta seguinte.
_TIMEOUT_SEGUNDOS = 6.0

#: Cooldown padrao por chave de evento (1 hora).
COOLDOWN_PADRAO_SEGUNDOS = 3600.0

#: Teto do Telegram por mensagem. Cortar aqui evita um 400 por tamanho.
_LIMITE_TEXTO = 4000

_lock = threading.Lock()
#: `{chave: momento do ultimo envio}` - process-local, some no restart. E o
#: suficiente: o agendador e um processo so, e um restart e justamente
#: quando reavisar faz sentido.
_ultimo_envio: dict[str, float] = {}


def configurado() -> bool:
    settings = get_settings()
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def _pode_enviar(chave: str | None, cooldown: float) -> bool:
    if chave is None:
        return True
    agora = time.monotonic()
    with _lock:
        anterior = _ultimo_envio.get(chave)
        if anterior is not None and (agora - anterior) < cooldown:
            return False
        _ultimo_envio[chave] = agora
    return True


def limpar_cooldowns() -> None:
    """So para teste - zera a memoria de quem ja foi avisado."""
    with _lock:
        _ultimo_envio.clear()


def enviar(
    texto: str,
    chave: str | None = None,
    cooldown_segundos: float = COOLDOWN_PADRAO_SEGUNDOS,
) -> bool:
    """Manda uma mensagem. Devolve se foi de fato enviada.

    `chave` agrupa eventos do mesmo tipo para o cooldown - ex.:
    `"tarefa-travada:itad"`. Sem chave, envia sempre (use so para o que e
    raro por natureza, como o resumo diario).

    Nunca levanta: sem configuracao, em cooldown, ou com o Telegram fora do
    ar, devolve `False` e a vida segue.
    """
    settings = get_settings()
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return False

    if not _pode_enviar(chave, cooldown_segundos):
        logger.debug("aviso suprimido por cooldown", extra={"chave": chave})
        return False

    try:
        resposta = requests.post(
            _URL.format(token=settings.telegram_bot_token),
            data={
                "chat_id": settings.telegram_chat_id,
                "text": texto[:_LIMITE_TEXTO],
                "disable_web_page_preview": "true",
            },
            timeout=_TIMEOUT_SEGUNDOS,
        )
        if resposta.status_code != 200:
            # O corpo do Telegram diz o motivo ("chat not found" quando
            # ninguem deu /start no bot, por exemplo) - sem ele o log nao
            # ajuda a consertar.
            logger.warning(
                "telegram recusou a mensagem",
                extra={
                    "status": resposta.status_code,
                    "corpo": resposta.text[:200],
                    "chave": chave,
                },
            )
            return False
    except Exception as exc:  # noqa: BLE001 - aviso nunca derruba quem avisa
        logger.warning(
            "falha ao enviar aviso pelo telegram",
            extra={"erro": f"{type(exc).__name__}: {exc}", "chave": chave},
        )
        return False

    return True
