"""O `Retry-After` do servidor tem teto.

**O bug real (2026-09-16).** `backoff_max` do urllib3 limita so o backoff
exponencial; o `Retry-After` do servidor passa intacto. Com `total=5`, um
servidor pedindo 1 hora prende o cliente por ate CINCO horas - dentro de uma
unica chamada, em `time.sleep`.

Isso derrubou o agendador local por 8 horas: o ITAD (atras da Cloudflare)
devolveu 429 com espera longa, e como as ~35 tarefas rodam em serie numa
thread so, TODAS pararam - `steam_online` (15 min), `vlr` e `lolesports` (5
min) ficaram um dia inteiro sem coletar. CPU em 0%, nenhuma linha de log.

O teto nao desrespeita o servidor: a espera e honrada ate o limite, e acima
dele a tentativa falha e a tarefa volta pra fila - custa uma rodada em vez
do dia.
"""

from __future__ import annotations

from services.collectors.http_client import (
    ESPERA_MAXIMA_SEGUNDOS,
    RateLimitedClient,
    _RetryComTeto,
)


class _RespostaFalsa:
    """O minimo que `Retry.get_retry_after` consulta."""

    def __init__(self, retry_after: str | None) -> None:
        self._valor = retry_after
        self.headers = {"Retry-After": retry_after} if retry_after else {}

    def getheader(self, nome: str, padrao=None):
        if nome.lower() == "retry-after":
            return self._valor
        return padrao


def _retry() -> _RetryComTeto:
    return _RetryComTeto(total=5, respect_retry_after_header=True)


def test_espera_curta_e_respeitada():
    """O motivo de `respect_retry_after_header` existir continua valendo: o
    429 curto de quem so quer que a gente desacelere e obedecido."""
    assert _retry().get_retry_after(_RespostaFalsa("30")) == 30


def test_espera_longa_e_limitada_ao_teto():
    """O caso que travou o agendador: uma hora vira o teto."""
    assert _retry().get_retry_after(_RespostaFalsa("3600")) == ESPERA_MAXIMA_SEGUNDOS


def test_sem_cabecalho_nao_inventa_espera():
    assert _retry().get_retry_after(_RespostaFalsa(None)) is None


def test_o_teto_e_menor_que_o_intervalo_das_tarefas_rapidas():
    """Fixa a premissa que justifica o numero: o teto tem que caber no
    intervalo da tarefa mais frequente (5 min), senao uma unica espera ja
    atrasaria a proxima rodada dela."""
    assert ESPERA_MAXIMA_SEGUNDOS < 5 * 60


def test_o_cliente_usa_o_retry_com_teto():
    """Sem isto, a classe existiria e nao seria usada - o bug voltaria
    inteiro sem nenhum teste ficar vermelho."""
    cliente = RateLimitedClient(nome="teste", intervalo_minimo=0)
    try:
        adaptador = cliente.session.get_adapter("https://exemplo.invalido")
        assert isinstance(adaptador.max_retries, _RetryComTeto)
    finally:
        cliente.close()
