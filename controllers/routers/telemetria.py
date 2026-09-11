"""Telemetria de acesso ao site - pageview/heartbeat, sem PII.

Um endpoint so, publico, chamado pelo frontend (`App.tsx`) no carregamento,
a cada troca de rota, e num intervalo enquanto a aba fica aberta. Alimenta
duas coisas ao mesmo tempo:

1. `fato_acesso_site` - o historico persistido, o que o painel admin usa pra
   "acessos por dia/mes/ano" e "visitantes unicos".
2. `services/ml/telemetria_site` - presenca em memoria, o que vira "quantas
   pessoas estao no site agora".

`visitante_id` e um UUID que o frontend gera e guarda no localStorage - da
pra contar visitante unico sem cookie, sem IP, sem nada que identifique uma
pessoa de verdade.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from views.schemas import EntradaAcesso
from models.models import FatoAcessoSite, FatoBusca
from models.session import session_scope
from services.ml import telemetria_site

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telemetria", tags=["telemetria"])


@router.post("/acesso", status_code=204)
def registrar_acesso(entrada: EntradaAcesso) -> None:
    """Grava o pageview/heartbeat. Nunca falha de um jeito que quebre a tela -
    telemetria e acessorio, se o banco estiver fora do ar o pior caso e um
    ponto a menos no grafico, nao um erro pro usuario."""
    telemetria_site.registrar_presenca(entrada.visitante_id)
    try:
        with session_scope() as sessao:
            sessao.add(
                FatoAcessoSite(
                    visitante_id=entrada.visitante_id,
                    rota=entrada.rota,
                    criado_em=datetime.now(timezone.utc),
                )
            )
    except Exception as exc:  # noqa: BLE001 - telemetria nao pode derrubar a tela
        logger.warning(
            "gravar acesso falhou", extra={"erro": f"{type(exc).__name__}: {exc}"}
        )


def registrar_busca(fonte: str, termo: str, resultados: int) -> None:
    """Log de uma busca no catalogo - `catalogo.py` (Steam) e `xbox.py` chamam
    isto no fim do endpoint de busca deles.

    Sessao propria (`session_scope`), nao a `Depends(get_db)` do endpoint que
    chama: aquela e so leitura e ninguem da commit nela, e telemetria nao
    pode arriscar quebrar (ou silenciosamente nao gravar) a busca de verdade.
    """
    try:
        with session_scope() as sessao:
            sessao.add(
                FatoBusca(
                    fonte=fonte,
                    termo=termo[:200],
                    resultados=resultados,
                    criado_em=datetime.now(timezone.utc),
                )
            )
    except Exception as exc:  # noqa: BLE001 - telemetria nao pode derrubar a busca
        logger.warning(
            "gravar busca falhou",
            extra={"fonte": fonte, "erro": f"{type(exc).__name__}: {exc}"},
        )
