"""A home: o que está acontecendo agora e o confronto em destaque.

`GET /api/home/destaques` junta duas coisas numa chamada só:

- **`ao_vivo`** — os próximos confrontos de TODOS os jogos numa janela de -6 h a
  +10 dias, sem resultado, deduplicados por partida (a mesma partida pode vir
  de duas fontes com `id_externo` diferente). Cada um traz o jogo, os dois
  times com escudo e o horário; `ao_vivo=true` quando já passou do horário
  previsto e ainda não tem placar.
- **`destaque`** — UM confronto com a probabilidade do modelo: o mais próximo
  entre os que têm os dois times reconciliados num jogo com modelo ajustado.
  É o que alimenta o velocímetro da home. `None` quando nenhum candidato serve.

O payload inteiro é cacheado por 3 min: cada `destaque` roda `prever()`, que
carrega o modelo e o histórico do jogo, e a home é a rota mais batida do site.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from views.schemas import ConfrontoAoVivo, DestaqueConfronto, DestaquesHome
from models.models import AgendaPartida, DimEquipe, DimJogo
from models.session import get_db
from services.ml import confronto as motor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/home", tags=["home"])

#: Ordem de preferência de fonte quando a mesma partida vem duplicada. `ps:` é
#: o prefixo que o `carregar_agenda` da PandaScore usa para times não casados.
_PRIO_FONTE = ("vlr:", "pandascore:", "ps:", "hltv:")

#: Cache de processo do payload inteiro. TTL curto: a agenda muda devagar e o
#: cálculo do destaque é o gargalo.
_CACHE: dict[str, tuple[float, DestaquesHome]] = {}
_TTL_SEGUNDOS = 180.0
#: Quantos candidatos tentar antes de desistir do destaque — os mais próximos
#: primeiro, e quase sempre o primeiro (Dota/CS/Valorant) tem modelo.
_MAX_TENTATIVAS = 6


def _prioridade_fonte(id_externo: str) -> int:
    for indice, prefixo in enumerate(_PRIO_FONTE):
        if id_externo.startswith(prefixo):
            return indice
    return len(_PRIO_FONTE)


def _chave_time(nome: str) -> str:
    """`The MongolZ` e `TheMongolz` viram a mesma chave de dedup."""
    return re.sub(r"[^a-z0-9]", "", nome.lower())


@router.get("/destaques", response_model=DestaquesHome)
def destaques(db: Session = Depends(get_db)) -> DestaquesHome:
    """Confrontos ao vivo/por vir de todos os jogos + o destaque com previsão."""
    em_cache = _CACHE.get("destaques")
    if em_cache is not None and time.monotonic() - em_cache[0] < _TTL_SEGUNDOS:
        return em_cache[1]

    agora = datetime.now(timezone.utc)
    equipe_a = aliased(DimEquipe)
    equipe_b = aliased(DimEquipe)

    linhas = db.execute(
        select(
            AgendaPartida.id_externo,
            DimJogo.codigo,
            DimJogo.nome,
            AgendaPartida.equipe_a_nome,
            AgendaPartida.equipe_b_nome,
            AgendaPartida.id_equipe_a,
            AgendaPartida.id_equipe_b,
            AgendaPartida.inicio_previsto,
            AgendaPartida.torneio,
            AgendaPartida.formato,
            equipe_a.logo_url,
            equipe_a.tag,
            equipe_b.logo_url,
            equipe_b.tag,
            AgendaPartida.detalhe,
        )
        .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
        .outerjoin(equipe_a, equipe_a.id_equipe == AgendaPartida.id_equipe_a)
        .outerjoin(equipe_b, equipe_b.id_equipe == AgendaPartida.id_equipe_b)
        .where(
            AgendaPartida.vitoria_a.is_(None),
            AgendaPartida.inicio_previsto >= agora - timedelta(hours=6),
            AgendaPartida.inicio_previsto <= agora + timedelta(days=10),
        )
        .order_by(AgendaPartida.inicio_previsto)
        .limit(160)
    ).all()

    # "Acontecendo agora" só vale se estiver MESMO acontecendo. A verdade é o
    # `status` da PandaScore em `detalhe`; sem ele (vlr/hltv/Liquipedia), a
    # heurística é o horário: começou há menos de 90 min ou ainda vai começar.
    vivos: list[tuple] = []
    for linha in linhas:
        detalhe = linha[14] or {}
        status = detalhe.get("status")
        inicio = linha[7]
        if status in ("finished", "canceled", "postponed"):
            continue
        rodando = status == "running"
        comecou_ha_pouco = inicio <= agora and inicio >= agora - timedelta(minutes=90)
        vai_comecar = inicio > agora
        if rodando or comecou_ha_pouco or vai_comecar:
            vivos.append(linha)

    # Dedup: a mesma partida (jogo + dois times + dia) pode chegar de duas
    # fontes. Fica a de maior prioridade — e `running` ganha de tudo.
    def _rank(linha: tuple) -> tuple[int, int]:
        rodando = (linha[14] or {}).get("status") == "running"
        return (0 if rodando else 1, _prioridade_fonte(linha[0]))

    vistos: dict[tuple, tuple] = {}
    for linha in vivos:
        times = frozenset((_chave_time(linha[3]), _chave_time(linha[4])))
        chave = (linha[1], times, linha[7].date())
        atual = vistos.get(chave)
        if atual is None or _rank(linha) < _rank(atual):
            vistos[chave] = linha
    dedup = sorted(vistos.values(), key=lambda linha: linha[7])

    def _monta(linha: tuple, **extra) -> dict:
        detalhe = linha[14] or {}
        status = detalhe.get("status")
        inicio = linha[7]
        return dict(
            id_externo=linha[0],
            jogo=linha[1],
            jogo_nome=linha[2],
            equipe_a_nome=linha[3],
            equipe_b_nome=linha[4],
            equipe_a_logo=linha[10],
            equipe_a_tag=linha[11],
            equipe_b_logo=linha[12],
            equipe_b_tag=linha[13],
            torneio=linha[8],
            formato=linha[9],
            inicio_previsto=inicio,
            ao_vivo=status == "running" or (inicio <= agora and status != "not_started"),
            streams=detalhe.get("streams") or [],
            **extra,
        )

    ao_vivo = [ConfrontoAoVivo(**_monta(linha)) for linha in dedup[:12]]

    resposta = DestaquesHome(ao_vivo=ao_vivo, destaque=_destaque(dedup, agora, _monta))
    _CACHE["destaques"] = (time.monotonic(), resposta)
    return resposta


def _destaque(dedup: list[tuple], agora, monta) -> DestaqueConfronto | None:
    """O confronto mais próximo com previsão, entre os candidatos reconciliados.

    Prefere os que ainda não começaram — a previsão é "antes da partida" — mas
    aceita um ao vivo se for o único candidato com modelo.
    """
    candidatos = [linha for linha in dedup if linha[5] and linha[6]]
    candidatos.sort(key=lambda linha: (linha[7] <= agora, linha[7]))
    for linha in candidatos[:_MAX_TENTATIVAS]:
        try:
            previsao = motor.prever(linha[5], linha[6], linha[1])
        except (FileNotFoundError, KeyError, ValueError) as exc:
            logger.debug(
                "destaque descartado",
                extra={"jogo": linha[1], "erro": f"{type(exc).__name__}: {exc}"},
            )
            continue
        return DestaqueConfronto(
            **monta(linha, probabilidade_a=round(previsao.probabilidade_a, 4))
        )
    return None
