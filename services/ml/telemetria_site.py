"""Quem esta no site AGORA - em memoria, por processo.

Nao da pra responder "quantas pessoas estao acessando agora" so com
`fato_acesso_site` (o historico persistido): teria que decidir uma janela e
reconsultar o banco a cada refresh do painel, e continuaria sem saber se um
visitante ainda esta com a aba aberta. Aqui e mais simples: o frontend manda
um heartbeat a cada ~45s enquanto a aba esta aberta
(`POST /api/telemetria/acesso`), e "online agora" e "quantos visitantes
mandaram heartbeat nos ultimos N segundos".

Por processo, nao persistido - reinicia com o container, que e exatamente o
que se quer de "agora" (nao "historico"). Mesmo padrao de
`services/ml/telemetria_assistente.py`.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

#: Sem heartbeat por mais que isto, o visitante conta como "saiu".
#: Um pouco mais que o intervalo do heartbeat do frontend (45s) para
#: tolerar uma chamada perdida sem sumir da contagem.
JANELA_ONLINE = timedelta(seconds=90)

#: Teto de visitantes guardados - protege contra crescimento sem fim se
#: alguem martelar o endpoint com `visitante_id`s diferentes. Bem acima do
#: trafego real esperado do site.
MAX_VISITANTES = 5000

_lock = threading.Lock()
_ultimo_visto: dict[str, datetime] = {}


def registrar_presenca(visitante_id: str) -> None:
    """Marca `visitante_id` como visto agora. Chamar a cada acesso/heartbeat."""
    if not visitante_id:
        return
    agora = datetime.now(timezone.utc)
    with _lock:
        if len(_ultimo_visto) >= MAX_VISITANTES and visitante_id not in _ultimo_visto:
            _podar(agora)
        _ultimo_visto[visitante_id] = agora


def _podar(agora: datetime) -> None:
    """Sem lock proprio - chamar so de dentro de um `with _lock`."""
    corte = agora - JANELA_ONLINE
    mortos = [vid for vid, visto in _ultimo_visto.items() if visto < corte]
    for vid in mortos:
        del _ultimo_visto[vid]


def online_agora() -> int:
    """Quantos visitantes mandaram heartbeat dentro da janela."""
    agora = datetime.now(timezone.utc)
    with _lock:
        _podar(agora)
        return len(_ultimo_visto)
