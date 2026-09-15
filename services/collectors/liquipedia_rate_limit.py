"""Circuit breaker compartilhado do rate limit da Liquipedia (HTML/wikitext).

Um 429 e sinal do SERVIDOR de "voce esta sendo limitado" - diferente de um
erro de UMA wiki/torneio/lote (404, parse quebrado, timeout pontual), que
nunca deveria derrubar o resto da varredura. Antes deste circuit breaker,
um 429 so pulava pro proximo item da lista e tentava de novo - que, contra
um rate limit de verdade, significa martelar a mesma parede em toda
wiki/torneio/lote seguinte, sem nunca recuar. Foi exatamente isso que
aconteceu em 2026-09-15: ficou martelando por mais de 2h seguidas (local e
VPS ao mesmo tempo) ate ser parado na mao.

Compartilhado entre TODO coletor de Liquipedia via HTML (agenda/equipes/
brackets/OWCS) porque todos batem no mesmo host e a mesma politica de
abuso - um 429 em qualquer um deles pausa os outros tambem.

Estado em memoria, de proposito: perde-se no restart do processo, e perder
so significa uma tentativa cedo demais na proxima subida, nunca um
martelamento repetido.
"""

from __future__ import annotations

import time


class LiquipediaBloqueadaError(RuntimeError):
    """A Liquipedia devolveu 429 recentemente - nem tenta de novo ainda."""


#: Bem mais longo que o reagendamento normal de falha do agendador (300s) -
#: um rate limit de verdade nao passa em 5 minutos (o bloqueio real durou
#: mais de 2h). Ajustavel aqui se a Liquipedia confirmar um numero oficial.
ESPERA_APOS_429_SEGUNDOS = 3600

_bloqueado_ate: float = 0.0


def eh_429(exc: BaseException) -> bool:
    """`True` quando a excecao e um `HTTPError` de status 429."""
    resposta = getattr(exc, "response", None)
    return getattr(resposta, "status_code", None) == 429


def checar() -> None:
    """Levanta `LiquipediaBloqueadaError` se ainda em cooldown.

    Chamado NO INICIO de cada coleta - uma checagem em memoria, sem custo
    de rede, entao o agendador pode tentar de novo no proprio ritmo normal
    de falha (`ESPERA_APOS_FALHA_SEGUNDOS`) sem gastar chamada nenhuma
    enquanto o cooldown nao passar.
    """
    if time.monotonic() < _bloqueado_ate:
        restante = round(_bloqueado_ate - time.monotonic())
        raise LiquipediaBloqueadaError(
            f"Liquipedia em cooldown por 429 recente - proxima tentativa em {restante}s"
        )


def acionar() -> None:
    """Registra um 429 visto agora - todo coletor de Liquipedia HTML fica
    parado ate o cooldown passar, nao so o que viu o erro."""
    global _bloqueado_ate
    _bloqueado_ate = time.monotonic() + ESPERA_APOS_429_SEGUNDOS


def esta_bloqueada() -> bool:
    """Versao que nao levanta - pra um laco externo saber que um coletor
    interno ja acionou o breaker (sem ter deixado a excecao subir) e parar
    de rodar mais itens (ex.: a proxima wiki do rodizio)."""
    return time.monotonic() < _bloqueado_ate
