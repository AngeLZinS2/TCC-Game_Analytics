"""Resumo de avaliacoes por IA - "o que a comunidade esta dizendo desse jogo?"

Amostra avaliacoes de texto de `fato_avaliacao_steam` (metade recomendadas,
metade nao) e pede pro Groq (`llama-3.3-70b-versatile`, gratis) um resumo em
portugues + pontos positivos/negativos. Cacheia em `dim_jogo_steam`, igual ao
`itad_id`/`menor_preco_historico` de outras fontes externas.

**Conta e chave SEPARADAS do assistente** (`OPENROUTER_API_KEY`): o Groq
gratis da 1000 req/dia e 200 mil tokens/dia (o OpenRouter free da so 50
req/dia sem credito) - orcamento suficiente pra cobrir o catalogo inteiro sem
competir com quem esta conversando com o assistente ao vivo.

**Sem `GROQ_API_KEY` o coletor recusa rodar** - o painel "Resumo por IA" nao
aparece. Estado esperado, como o assistente sem OpenRouter.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from sqlalchemy import func, or_, select

from services.collectors.base import BaseCollector, RawRecord
from services.collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from models.models import DimJogoSteam, FatoAvaliacaoSteam
from models.session import session_scope
from services.ml.sentimento import MINIMO_CARACTERES
from services.etl.load_resumo_reviews import carregar
from services.etl.transform_resumo_reviews import (
    ENDPOINT_CHAT,
    FONTE,
    ResultadoResumoReviews,
    transformar,
)

logger = logging.getLogger(__name__)

#: Jogos processados por rodada do agendador. O que limita nao e o teto de
#: 1000 requisicoes/dia do Groq, e o de 200 mil tokens/dia - a rodada de 2h
#: (ver `config.agendador_resumo_reviews_minutos`) cobre o catalogo inteiro
#: (~50 jogos) em menos de um dia com folga.
POR_RODADA = 6

#: Segundos entre chamadas ao Groq. O limite deles e 30/min; 2,1s da folga.
INTERVALO_SEGUNDOS = 2.1

INSTRUCAO = (
    "Voce resume avaliacoes de jogadores da Steam sobre um jogo, em portugues "
    "do Brasil, para o publico de um site de analytics de jogos. Leia as "
    "avaliacoes reais abaixo (algumas podem estar em outros idiomas - "
    "entenda e resuma em portugues mesmo assim) e responda SOMENTE no formato:\n\n"
    "RESUMO: <2 a 4 frases sobre a recepcao geral, sem citar numero de "
    "avaliacoes>\n"
    "POSITIVOS:\n"
    "- <ponto forte citado com frequencia>\n"
    "- <ponto forte citado com frequencia>\n"
    "- <ponto forte citado com frequencia>\n"
    "NEGATIVOS:\n"
    "- <critica citada com frequencia>\n"
    "- <critica citada com frequencia>\n"
    "- <critica citada com frequencia>\n\n"
    "Regras: baseie-se SO no que as avaliacoes dizem, nunca invente. Se quase "
    "nao houver criticas recorrentes, liste menos itens em NEGATIVOS (nunca "
    "complete com algo que ninguem escreveu). Nao use markdown alem dos "
    "tracos das listas. Nao repita o nome do jogo em toda linha."
)


class SemChaveGroqError(RuntimeError):
    """`GROQ_API_KEY` nao configurada - o coletor nao tem o que fazer."""


def jogos_para_resumir(
    limite: int | None,
    settings: Settings,
    app_ids: Sequence[int] | None = None,
) -> list[int]:
    """`app_id`s que valem receber (ou renovar) um resumo por IA.

    Precisa de `resumo_reviews_minimo_avaliacoes` avaliacoes com texto util
    (>= MINIMO_CARACTERES, o mesmo piso do classificador de sentimento) e
    nunca ter sido resumido, ou o resumo ja ter passado de
    `resumo_reviews_revalidar_dias`. Prioriza quem nunca teve resumo e, entre
    esses, quem tem mais avaliacoes (mais material pra sintetizar).
    """
    corte = datetime.now(timezone.utc) - timedelta(
        days=settings.resumo_reviews_revalidar_dias
    )
    with session_scope() as sessao:
        contagem = (
            select(
                FatoAvaliacaoSteam.app_id,
                func.count().label("n"),
            )
            .where(func.length(FatoAvaliacaoSteam.texto) >= MINIMO_CARACTERES)
            .group_by(FatoAvaliacaoSteam.app_id)
            .subquery()
        )
        consulta = (
            select(DimJogoSteam.app_id)
            .join(contagem, contagem.c.app_id == DimJogoSteam.app_id)
            .where(
                contagem.c.n >= settings.resumo_reviews_minimo_avaliacoes,
                or_(
                    DimJogoSteam.resumo_reviews_em.is_(None),
                    DimJogoSteam.resumo_reviews_em < corte,
                ),
            )
            .order_by(
                DimJogoSteam.resumo_reviews_em.asc().nulls_first(),
                contagem.c.n.desc(),
            )
        )
        if app_ids is not None:
            consulta = consulta.where(DimJogoSteam.app_id.in_(list(app_ids)))
        if limite:
            consulta = consulta.limit(limite)
        return [linha[0] for linha in sessao.execute(consulta)]


def _amostra_avaliacoes(
    sessao: Any, app_id: int, tamanho: int
) -> list[tuple[str, bool]]:
    """`tamanho//2` recomendadas + `tamanho//2` nao-recomendadas, mais recentes primeiro."""
    metade = max(1, tamanho // 2)
    linhas: list[tuple[str, bool]] = []
    for recomendado in (True, False):
        consulta = (
            select(FatoAvaliacaoSteam.texto, FatoAvaliacaoSteam.recomendado)
            .where(
                FatoAvaliacaoSteam.app_id == app_id,
                FatoAvaliacaoSteam.recomendado.is_(recomendado),
                func.length(FatoAvaliacaoSteam.texto) >= MINIMO_CARACTERES,
            )
            .order_by(FatoAvaliacaoSteam.criada_em.desc().nulls_last())
            .limit(metade)
        )
        linhas.extend((texto, rec) for texto, rec in sessao.execute(consulta))
    return linhas


def _prompt_avaliacoes(amostra: list[tuple[str, bool]]) -> str:
    blocos = []
    for texto, recomendado in amostra:
        rotulo = "RECOMENDA" if recomendado else "NAO RECOMENDA"
        aparado = texto.strip().replace("\n", " ")[:320]
        blocos.append(f"[{rotulo}] {aparado}")
    return "\n".join(blocos)


class ResumoReviewsCollector(BaseCollector[ResultadoResumoReviews]):
    fonte = FONTE

    def __init__(
        self,
        raw_storage: Any,
        settings: Settings | None = None,
        limite: int | None = None,
        app_ids: Sequence[int] | None = None,
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.limite = limite if limite is not None else POR_RODADA
        #: Quando setado, resume so esses apps (uso manual/teste).
        self.app_ids = list(app_ids) if app_ids is not None else None
        self.falhas = 0

        self.client = RateLimitedClient(
            nome="groq",
            intervalo_minimo=INTERVALO_SEGUNDOS,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.groq_timeout_seconds,
        )

    @property
    def _base(self) -> str:
        return self.settings.groq_base_url.rstrip("/")

    def collect(self) -> list[RawRecord]:
        if not self.settings.groq_api_key:
            raise SemChaveGroqError(
                "GROQ_API_KEY nao configurada. Pegue a chave gratuita em "
                "https://console.groq.com/keys e coloque no .env."
            )

        alvos = jogos_para_resumir(self.limite, self.settings, self.app_ids)
        if not alvos:
            logger.info("nenhum jogo pendente de resumo por IA")
            return []

        registros: list[RawRecord] = []
        with session_scope() as sessao:
            nomes = dict(
                sessao.execute(
                    select(DimJogoSteam.app_id, DimJogoSteam.nome).where(
                        DimJogoSteam.app_id.in_(alvos)
                    )
                )
            )
            for app_id in alvos:
                amostra = _amostra_avaliacoes(
                    sessao, app_id, self.settings.resumo_reviews_amostra
                )
                if not amostra:
                    continue
                nome = nomes.get(app_id, str(app_id))
                mensagens = [
                    {"role": "system", "content": INSTRUCAO},
                    {
                        "role": "user",
                        "content": (
                            f"JOGO: {nome}\n\nAVALIACOES:\n"
                            f"{_prompt_avaliacoes(amostra)}"
                        ),
                    },
                ]
                try:
                    resposta = self.client.post_json(
                        f"{self._base}/chat/completions",
                        json={
                            "model": self.settings.groq_model,
                            "messages": mensagens,
                            "max_tokens": 600,
                            "temperature": 0.3,
                        },
                        headers={
                            "Authorization": f"Bearer {self.settings.groq_api_key}"
                        },
                    )
                except Exception as exc:  # noqa: BLE001 - um jogo nao derruba os outros
                    self.falhas += 1
                    logger.warning(
                        "resumo por IA falhou",
                        extra={
                            "app_id": app_id,
                            "erro": f"{type(exc).__name__}: {exc}",
                        },
                    )
                    continue

                if isinstance(resposta, dict) and resposta.get("error"):
                    self.falhas += 1
                    logger.warning(
                        "Groq recusou o resumo",
                        extra={"app_id": app_id, "erro": str(resposta["error"])[:200]},
                    )
                    continue

                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint=ENDPOINT_CHAT,
                        identificador=str(app_id),
                        payload={
                            "groq_response": resposta,
                            "amostra": {"total": len(amostra)},
                        },
                    )
                )
        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoResumoReviews:
        return transformar(registros)

    def load(self, resultado: ResultadoResumoReviews) -> int:
        return carregar(resultado)

    def close(self) -> None:
        self.client.close()
