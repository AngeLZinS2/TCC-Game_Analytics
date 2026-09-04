"""Normalizacao dos payloads do HowLongToBeat (tempo estimado pra zerar).

O HLTB nao tem API oficial nem Steam appid no payload - so da pra achar o
jogo por NOME, na busca de texto livre do proprio site. Isso tem duas
consequencias que o ITAD (que casa por appid exato) nao tem:

1. **O casamento e por similaridade, nao por igualdade.** A busca por
   "007 First Light" pode devolver dezenas de jogos com "007" no nome; o
   candidato certo e o mais parecido (`_melhor_candidato`), e abaixo de
   `LIMIAR_SIMILARIDADE` e melhor nao casar do que casar errado - mostrar o
   tempo de "007 Racing" na ficha de "007 First Light" seria pior que nao
   mostrar nada.
2. **`parse()` precisa do nome usado na busca**, que o payload sozinho nao
   carrega (a resposta da busca so tem os *candidatos*, nao o termo). Por
   isso o coletor grava `{"app_id", "consulta", "resultado"}` como payload
   bruto em vez de so a resposta crua da API - preserva o suficiente pra
   `parse()` continuar uma funcao pura sobre o RawRecord, inclusive relido do
   disco.

Tempos chegam em SEGUNDOS (`comp_main`, `comp_plus`, `comp_100`); convertidos
pra horas com 1 casa decimal, a unidade que a tela mostra.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Iterable

from pydantic import BaseModel, Field

from collectors.base import RawRecord

logger = logging.getLogger(__name__)

FONTE = "hltb"
ENDPOINT_BUSCA = "search"

#: Abaixo disso, o candidato mais parecido ainda assim e provavelmente outro
#: jogo. 0.5 deixa passar diferenca de subtitulo/edicao mas barra jogos
#: completamente diferentes que so compartilham uma palavra do nome.
LIMIAR_SIMILARIDADE = 0.5


class TempoJogoHltb(BaseModel):
    app_id: int
    hltb_id: str
    nome_hltb: str
    horas_historia: Decimal | None = None
    horas_extras: Decimal | None = None
    horas_completista: Decimal | None = None


class ResultadoHltb(BaseModel):
    #: app_ids que foram procurados e NENHUM candidato bateu com confianca
    #: suficiente - viram `hltb_id=""` em `dim_jogo_steam` para nao repetir.
    sem_hltb: list[int] = Field(default_factory=list)
    jogos: list[TempoJogoHltb] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.jogos)


def _similaridade(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _melhor_candidato(nome_steam: str, candidatos: list[Any]) -> dict | None:
    """O candidato da busca mais parecido com `nome_steam`, ou `None`.

    Confere nome e apelido (`game_alias`) - o HLTB guarda "Hades 2" como
    apelido de "Hades II", por exemplo - e fica com o melhor dos dois.
    """
    melhor: dict | None = None
    melhor_score = 0.0
    for item in candidatos:
        if not isinstance(item, dict) or not item.get("game_id"):
            continue
        score = max(
            _similaridade(nome_steam, str(item.get("game_name") or "")),
            _similaridade(nome_steam, str(item.get("game_alias") or "")),
        )
        if score > melhor_score:
            melhor_score, melhor = score, item
    if melhor is None or melhor_score < LIMIAR_SIMILARIDADE:
        return None
    return melhor


def _horas(segundos: Any) -> Decimal | None:
    """Segundos (like `comp_main`) -> horas com 1 casa. `0`/`None` vira `None`.

    Zero no HLTB significa "ninguem registrou tempo ainda", nao "zero horas" -
    mostrar "0h" na tela afirmaria um dado que na verdade nao existe.
    """
    if not isinstance(segundos, (int, float)) or segundos <= 0:
        return None
    return Decimal(str(round(segundos / 3600, 1)))


def transformar(registros: Iterable[RawRecord]) -> ResultadoHltb:
    """Escolhe o melhor candidato de cada busca e converte os tempos."""
    resultado = ResultadoHltb()

    for registro in registros:
        if registro.fonte != FONTE or registro.endpoint != ENDPOINT_BUSCA:
            continue

        payload = registro.payload if isinstance(registro.payload, dict) else {}
        app_id = payload.get("app_id")
        if app_id is None:
            continue
        nome = str(payload.get("consulta") or "")
        candidatos = ((payload.get("resultado") or {}).get("data")) or []

        melhor = _melhor_candidato(nome, candidatos)
        if melhor is None:
            resultado.sem_hltb.append(int(app_id))
            continue

        resultado.jogos.append(
            TempoJogoHltb(
                app_id=int(app_id),
                hltb_id=str(melhor["game_id"]),
                nome_hltb=str(melhor.get("game_name") or ""),
                horas_historia=_horas(melhor.get("comp_main")),
                horas_extras=_horas(melhor.get("comp_plus")),
                horas_completista=_horas(melhor.get("comp_100")),
            )
        )

    return resultado
