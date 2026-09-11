"""Telemetria em memoria das chamadas ao OpenRouter.

Existe porque o `/auth/key` do OpenRouter nao devolve quanto falta da cota
gratis (so custo em dolar, que fica em 0 pra modelo `:free` seja qual for o
volume de chamadas) - a unica forma de saber "esta rate-limited agora" e
observar as nossas proprias chamadas. O painel "Status da API" do Assistente
de Dados le isto pra explicar um 429 na hora, em vez de parecer bug nosso.

Por processo, nao persistido: reinicia com o container, e e exatamente o
que se quer de um indicador "agora" - historico de um deploy anterior nao
ajuda a entender um 429 que acabou de acontecer.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Deque

#: Quantas chamadas recentes ficam guardadas. Cobre bem mais que uma sessao
#: de uso tipica sem crescer sem limite.
MAX_HISTORICO = 30

#: Janela pra "rate-limited agora": um 429 dentro disso ainda conta como
#: "o provedor esta limitando", mesmo que a chamada mais recente tenha ido bem
#: (o limite e por minuto/dia no provedor, nao desaparece so por uma chamada OK).
JANELA_RATE_LIMIT = timedelta(minutes=5)


@dataclass(slots=True)
class _Chamada:
    quando: datetime
    sucesso: bool
    status_http: int | None
    erro: str | None
    duracao_ms: int

    @property
    def rate_limited(self) -> bool:
        return self.status_http == 429


_lock = threading.Lock()
_historico: Deque[_Chamada] = deque(maxlen=MAX_HISTORICO)


def registrar(
    *,
    sucesso: bool,
    status_http: int | None,
    erro: str | None,
    duracao_ms: int,
) -> None:
    """Guarda o resultado de uma chamada ao OpenRouter. Chamar de `_chamar_modelo`,
    tanto no sucesso quanto em cada ponto de falha."""
    with _lock:
        _historico.append(
            _Chamada(
                quando=datetime.now(timezone.utc),
                sucesso=sucesso,
                status_http=status_http,
                erro=erro[:200] if erro else None,
                duracao_ms=duracao_ms,
            )
        )


def resumo() -> dict:
    """Estado atual pro painel: taxa de sucesso recente, se esta rate-limited
    agora, e a lista de chamadas (mais recente primeiro)."""
    agora = datetime.now(timezone.utc)
    with _lock:
        chamadas = list(_historico)

    total = len(chamadas)
    sucessos = sum(1 for c in chamadas if c.sucesso)
    rate_limited_recente = any(
        c.rate_limited and (agora - c.quando) <= JANELA_RATE_LIMIT for c in chamadas
    )
    ultima = chamadas[-1] if chamadas else None

    return {
        "total_recente": total,
        "sucessos_recente": sucessos,
        "taxa_sucesso": round(sucessos / total, 4) if total else None,
        "rate_limited_recente": rate_limited_recente,
        "ultima_chamada_em": ultima.quando.isoformat() if ultima else None,
        "ultima_chamada_sucesso": ultima.sucesso if ultima else None,
        "ultima_chamada_erro": ultima.erro if ultima else None,
        "chamadas": [
            {
                "quando": c.quando.isoformat(),
                "sucesso": c.sucesso,
                "status_http": c.status_http,
                "rate_limited": c.rate_limited,
                "erro": c.erro,
                "duracao_ms": c.duracao_ms,
            }
            for c in reversed(chamadas)
        ],
    }
