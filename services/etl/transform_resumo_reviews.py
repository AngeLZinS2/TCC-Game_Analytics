"""Normalizacao do resumo de avaliacoes gerado pelo Groq.

Um so payload por jogo: a resposta crua de `chat/completions` (formato
OpenAI-compativel, igual ao `assistente.py` usa pro OpenRouter). O modelo e
instruido a responder num formato fixo:

    RESUMO: <2-4 frases>
    POSITIVOS:
    - item
    - item
    NEGATIVOS:
    - item
    - item

Modelo gratis nao segue formato 100% das vezes - acento em maiusculo,
markdown (`**RESUMO:**`), secao fora de ordem, secao faltando. O parser tolera
tudo isso; se nao achar NENHUM marcador reconhecivel, o texto inteiro vira o
resumo e as listas ficam vazias (degrada, nao descarta).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from pydantic import BaseModel, Field

from services.collectors.base import RawRecord

logger = logging.getLogger(__name__)

FONTE = "resumo_reviews"
ENDPOINT_CHAT = "chat/completions"

#: Quantos bullets de cada lado entram no resultado - o prompt pede ~4-5;
#: isto e so um teto contra um modelo que nao para de listar.
MAX_BULLETS = 6

_RE_RESUMO = re.compile(r"(?i)^\**#{0,3}\s*resumo\s*:?\**\s*")
_RE_POSITIVOS = re.compile(r"(?i)^\**#{0,3}\s*positivos\s*:?\**\s*$")
_RE_NEGATIVOS = re.compile(r"(?i)^\**#{0,3}\s*negativos\s*:?\**\s*$")
_RE_BULLET = re.compile(r"^[-*•]\s*")


class ResumoJogoReviews(BaseModel):
    app_id: int
    texto: str
    positivos: list[str] = Field(default_factory=list)
    negativos: list[str] = Field(default_factory=list)
    modelo: str
    avaliacoes_usadas: int


class ResultadoResumoReviews(BaseModel):
    resumos: list[ResumoJogoReviews] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.resumos)


def _extrair_secoes(bruto: str) -> tuple[str, list[str], list[str]]:
    """`RESUMO:`/`POSITIVOS:`/`NEGATIVOS:` -> `(resumo, positivos, negativos)`.

    Sem nenhum marcador reconhecido, devolve `bruto` inteiro como resumo.
    """
    secao: str | None = None
    partes_resumo: list[str] = []
    positivos: list[str] = []
    negativos: list[str] = []
    achou_marcador = False

    for linha_bruta in bruto.splitlines():
        linha = linha_bruta.strip()
        if not linha:
            continue

        if _RE_RESUMO.match(linha):
            secao = "resumo"
            achou_marcador = True
            resto = _RE_RESUMO.sub("", linha).strip()
            if resto:
                partes_resumo.append(resto)
            continue
        if _RE_POSITIVOS.match(linha):
            secao = "positivos"
            achou_marcador = True
            continue
        if _RE_NEGATIVOS.match(linha):
            secao = "negativos"
            achou_marcador = True
            continue

        item = _RE_BULLET.sub("", linha).strip()
        if not item:
            continue
        if secao == "resumo":
            partes_resumo.append(item)
        elif secao == "positivos":
            positivos.append(item)
        elif secao == "negativos":
            negativos.append(item)
        # secao is None (texto antes do 1o marcador) -> ignorado, e preambulo.

    if not achou_marcador:
        return bruto.strip(), [], []

    resumo = " ".join(partes_resumo).strip()
    return resumo, positivos[:MAX_BULLETS], negativos[:MAX_BULLETS]


def transformar(registros: Iterable[RawRecord]) -> ResultadoResumoReviews:
    resumos: list[ResumoJogoReviews] = []

    for registro in registros:
        if registro.fonte != FONTE or registro.endpoint != ENDPOINT_CHAT:
            continue
        payload = registro.payload
        if not isinstance(payload, dict):
            continue

        try:
            app_id = int(registro.identificador)
        except (TypeError, ValueError):
            continue

        resposta = payload.get("groq_response") or {}
        mensagem = ((resposta.get("choices") or [{}])[0].get("message")) or {}
        conteudo = (mensagem.get("content") or "").strip()
        if not conteudo:
            logger.warning("resposta do Groq sem conteudo", extra={"app_id": app_id})
            continue

        resumo, positivos, negativos = _extrair_secoes(conteudo)
        if not resumo:
            continue

        amostra = payload.get("amostra") or {}
        avaliacoes_usadas = int(amostra.get("total") or 0)

        resumos.append(
            ResumoJogoReviews(
                app_id=app_id,
                texto=resumo[:2000],
                positivos=positivos,
                negativos=negativos,
                modelo=str(resposta.get("model") or payload.get("modelo") or ""),
                avaliacoes_usadas=avaliacoes_usadas,
            )
        )

    return ResultadoResumoReviews(resumos=resumos)
