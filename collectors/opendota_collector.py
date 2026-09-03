"""Coletor de partidas profissionais de Dota 2 via OpenDota.

A API e publica e nao exige chave. O limite gratuito e de 60 requisicoes por
minuto e cerca de 3.000 por dia, informado nos cabecalhos
X-Rate-Limit-Remaining-Minute / -Day de cada resposta.

Fluxo de uma execucao:

    /heroes                      1 chamada   -> dim_personagem
    /proMatches (paginado)       N/100       -> descobre os match_ids
    /matches/{id}                1 por id    -> dim_partida + fato

Como o detalhe custa uma chamada por partida, o coletor consulta dim_partida
antes e pula o que ja foi coletado. Na pratica isso torna a segunda execucao
seguida quase gratuita em termos de rate limit.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import requests
from sqlalchemy import select

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from db.models import DimJogo, DimPartida
from db.session import session_scope
from etl.load_dota import carregar
from etl.transform_dota import (
    ENDPOINT_HEROIS,
    ENDPOINT_LISTA,
    ENDPOINT_PARTIDA,
    FONTE,
    JOGO,
    ResultadoDota,
    transformar,
)

logger = logging.getLogger(__name__)

URL_BASE = "https://api.opendota.com/api"
URL_HEROIS = f"{URL_BASE}/heroes"
URL_PRO_MATCHES = f"{URL_BASE}/proMatches"
URL_PARTIDA = f"{URL_BASE}/matches/{{match_id}}"

# Tamanho fixo do lote devolvido por /proMatches.
TAMANHO_LOTE = 100


class OpenDotaCollector(BaseCollector[ResultadoDota]):
    fonte = FONTE

    def __init__(
        self,
        raw_storage: Any,
        limite: int = 100,
        settings: Settings | None = None,
        pular_existentes: bool = True,
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.limite = max(1, limite)
        self.pular_existentes = pular_existentes
        self.falhas = 0

        cabecalhos = {}
        if self.settings.opendota_api_key:
            # A chave e opcional; so eleva o limite diario.
            cabecalhos["Authorization"] = f"Bearer {self.settings.opendota_api_key}"

        self.client = RateLimitedClient(
            nome="opendota",
            intervalo_minimo=self.settings.opendota_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
        )
        self.client.session.headers.update(cabecalhos)

    # -- descoberta de partidas ---------------------------------------------

    def listar_match_ids(self) -> list[int]:
        """Pagina /proMatches ate juntar `limite` ids, do mais recente ao mais antigo."""
        ids: list[int] = []
        menor_id: int | None = None

        while len(ids) < self.limite:
            params = {"less_than_match_id": menor_id} if menor_id else None
            lote = self.client.get_json(URL_PRO_MATCHES, params)
            if not isinstance(lote, list) or not lote:
                break

            do_lote = [
                int(item["match_id"])
                for item in lote
                if isinstance(item, dict) and item.get("match_id")
            ]
            if not do_lote:
                break

            ids.extend(do_lote)
            menor_id = min(do_lote)

            if len(lote) < TAMANHO_LOTE:
                break

        return ids[: self.limite]

    def filtrar_ja_coletadas(self, match_ids: Sequence[int]) -> list[int]:
        """Remove as partidas que ja estao em dim_partida - economia de rate limit."""
        if not self.pular_existentes or not match_ids:
            return list(match_ids)

        alvo = {str(match_id) for match_id in match_ids}
        try:
            with session_scope() as sessao:
                existentes = set(
                    sessao.scalars(
                        select(DimPartida.id_externo)
                        .join(DimJogo, DimJogo.id_jogo == DimPartida.id_jogo)
                        .where(DimJogo.codigo == JOGO)
                        .where(DimPartida.id_externo.in_(alvo))
                    ).all()
                )
        except Exception as exc:  # noqa: BLE001 - sem banco, coletamos tudo
            self.logger.warning(
                "nao foi possivel consultar partidas ja coletadas",
                extra={"erro": f"{type(exc).__name__}: {exc}"},
            )
            return list(match_ids)

        novas = [m for m in match_ids if str(m) not in existentes]
        if existentes:
            self.logger.info(
                "partidas ja coletadas foram puladas",
                extra={"puladas": len(existentes), "novas": len(novas)},
            )
        return novas

    # -- BaseCollector -------------------------------------------------------

    def collect(self) -> list[RawRecord]:
        registros: list[RawRecord] = []

        herois = self.client.get_json(URL_HEROIS)
        registros.append(
            RawRecord(
                fonte=self.fonte,
                endpoint=ENDPOINT_HEROIS,
                identificador="todos",
                payload=herois,
            )
        )

        match_ids = self.listar_match_ids()
        registros.append(
            RawRecord(
                fonte=self.fonte,
                endpoint=ENDPOINT_LISTA,
                identificador="ultimas",
                payload=match_ids,
            )
        )
        self.logger.info(
            "partidas descobertas", extra={"quantidade": len(match_ids)}
        )

        pendentes = self.filtrar_ja_coletadas(match_ids)
        total = len(pendentes)

        for posicao, match_id in enumerate(pendentes, start=1):
            self.logger.info(
                "coletando partida",
                extra={"partida": match_id, "posicao": posicao, "total": total},
            )
            registro = self._coletar_partida(match_id)
            if registro is not None:
                registros.append(registro)

        return registros

    def _coletar_partida(self, match_id: int) -> RawRecord | None:
        """Uma partida que falha nao aborta as demais."""
        try:
            payload = self.client.get_json(URL_PARTIDA.format(match_id=match_id))
        except (requests.RequestException, ValueError) as exc:
            self.falhas += 1
            self.logger.warning(
                "falha ao coletar partida",
                extra={
                    "partida": match_id,
                    "erro": f"{type(exc).__name__}: {exc}",
                },
            )
            return None

        return RawRecord(
            fonte=self.fonte,
            endpoint=ENDPOINT_PARTIDA,
            identificador=str(match_id),
            payload=payload,
        )

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoDota:
        return transformar(registros)

    def load(self, dados: ResultadoDota) -> int:
        return carregar(dados)

    def close(self) -> None:
        self.client.close()
