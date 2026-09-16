"""Varredura completa das ofertas ativas da Steam agora (Fase 35.1).

O que ja existia (`steam_catalogo.py` + `steam_collector.py`) so descobre
promocao por CATALOGO: indexa 186 mil apps por nome, mas nunca busca preco
deles - so os poucos "monitorados" e quem `price_change_number` sinalizar
como alterado DEPOIS do baseline. Resultado real, medido em 2026-09-15: 25
promocoes conhecidas contra 19.774 ofertas reais na Steam agora (mesma
contagem que `/specials` mostra pro usuario).

Este coletor cobre a lacuna direto: `/search/results/?specials=1` e o MESMO
endpoint AJAX que a propria pagina `/specials` chama pra se popular - nao
uma API alternativa, o dado que o usuario ve na tela. Paginado (100 por
pagina), da pra varrer tudo em ~200 chamadas por rodada, sem precisar de
`STEAM_API_KEY` (endpoint publico da loja).

**Duas varreduras, nao uma (2026-09-16).** A varredura sem filtro trazia as
19.963 ofertas de tudo que a loja vende - jogo, DLC, trilha sonora, video,
software - e a tela de Ofertas ficava cheia de "X Soundtrack" e "Y - Pack de
Temporada" no meio dos jogos. O buscador ja sabe separar pelo `category1`,
entao a varredura roda uma vez por tipo (998 = jogo, 21 = DLC) e cada linha
sai sabendo o que e. Efeito colateral desejado: o que nao e jogo nem DLC
(trilha sonora, video, software - as ~1.300 linhas restantes) simplesmente
nao entra mais.

O DLC continua sendo coletado porque a promocao dele importa - so nao na
lista de Ofertas: ela aparece na ficha do jogo dono da DLC (`dlc_ids`).
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from config import Settings, get_settings
from services.collectors.base import BaseCollector, RawRecord
from services.collectors.http_client import RateLimitedClient
from services.etl.load_steam_ofertas import carregar
from services.etl.transform_steam_ofertas import (
    FONTE,
    TIPO_DLC,
    TIPO_JOGO,
    ResultadoOfertasSteam,
    parse_dicionario_tags,
    parse_pagina,
)

logger = logging.getLogger(__name__)

URL_BUSCA = "https://store.steampowered.com/search/results/"

#: Dicionario publico de tags da Steam (id -> nome), no idioma da coleta.
#: Uma requisicao por varredura - os IDs ja vem de graca em cada linha da
#: busca, e so o nome precisa desta chamada.
URL_TAGS = "https://store.steampowered.com/tagdata/populartags/{idioma}"

#: Os dois endpoints nomeiam idioma de forma diferente - a busca quer
#: `l=portuguese`, o dicionario de tags responde em `/brazilian`. Ambos
#: verificados ao vivo; nao sao intercambiaveis.
IDIOMA_BUSCA = "portuguese"
IDIOMA_TAGS = "brazilian"

#: Testado ao vivo: 100 devolve 100 linhas por chamada, sem sinal de teto
#: menor documentado pra este endpoint.
RESULTADOS_POR_PAGINA = 100

#: `{tipo: category1}` - os dois tipos que a tela usa, e o codigo que o
#: buscador da Steam espera pra cada um. Conferido ao vivo em 2026-09-16
#: (998 devolve "Diablo IV", "Baldur's Gate 3"; 21 devolve "Monster Hunter
#: World: Iceborne", "F1 25: Pack de Temporada"). A ordem importa: o jogo e
#: o que a tela mostra, entao vem primeiro e, se a varredura de DLC falhar
#: no meio, o dado principal ja entrou.
CATEGORIA_POR_TIPO: dict[str, int] = {TIPO_JOGO: 998, TIPO_DLC: 21}

#: Trava de seguranca - bem acima do ~200 paginas observado (19.774 ofertas
#: em 2026-09-15) pra sobrar folga se o total crescer, mas finito o
#: suficiente pra nunca prender o laco do agendador half indefinidamente
#: se a Steam parar de mandar `have_more_results`/esvaziar a pagina.
MAX_PAGINAS = 400


class SteamOfertasCollector(BaseCollector[ResultadoOfertasSteam]):
    fonte = FONTE

    def __init__(self, raw_storage: Any, settings: Settings | None = None) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.falhas = 0

        self.client = RateLimitedClient(
            nome="steam-ofertas",
            intervalo_minimo=self.settings.steam_ofertas_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
        )
        #: Setado em `collect()`, lido em `parse()` - mesmo padrao de estado
        #: entre os dois passos que `SteamCatalogoCollector` ja usa.
        self._completa = False

    def collect(self) -> list[RawRecord]:
        registros: list[RawRecord] = []
        # So e "completa" se TODAS as varreduras terminarem: e esta flag que
        # autoriza o load a encerrar promocao ausente, e uma varredura de
        # DLC truncada nao pode encerrar as promocoes de DLC que faltaram.
        self._completa = True

        for tipo, categoria in CATEGORIA_POR_TIPO.items():
            if not self._varrer(tipo, categoria, registros):
                self._completa = False

        # O dicionario de tags fecha a varredura: os ids ja vieram em cada
        # linha acima, falta so o nome deles. Uma requisicao, e uma falha aqui
        # nao invalida as ofertas - a tela so fica sem o filtro de genero.
        try:
            dicionario = self.client.get_json(URL_TAGS.format(idioma=IDIOMA_TAGS))
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint="tags",
                    identificador=IDIOMA_TAGS,
                    payload=dicionario,
                )
            )
        except Exception as exc:  # noqa: BLE001 - o dicionario e acessorio
            self.falhas += 1
            self.logger.warning(
                "falha ao buscar dicionario de tags",
                extra={"erro": f"{type(exc).__name__}: {exc}"},
            )

        logger.info(
            "varredura de ofertas concluida",
            extra={"paginas": len(registros), "completa": self._completa},
        )
        return registros

    def _varrer(self, tipo: str, categoria: int, registros: list[RawRecord]) -> bool:
        """Varre um tipo (`category1`) inteiro. `True` se chegou ao fim real.

        Os registros brutos entram em `registros` com o tipo no
        `identificador` - e de la que `parse()` sabe, depois, se aquela
        pagina era de jogo ou de DLC.
        """
        total_count: int | None = None
        inicio = 0

        for pagina in range(1, MAX_PAGINAS + 1):
            try:
                resposta = self.client.get_json(
                    URL_BUSCA,
                    params={
                        "query": "",
                        "start": inicio,
                        "count": RESULTADOS_POR_PAGINA,
                        "specials": 1,
                        "infinite": 1,
                        "category1": categoria,
                        "cc": self.settings.steam_country,
                        "l": IDIOMA_BUSCA,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - uma pagina ruim nao perde as anteriores
                self.falhas += 1
                self.logger.warning(
                    "falha ao buscar pagina de ofertas - varredura fica "
                    "incompleta, nenhuma promocao ausente sera encerrada",
                    extra={
                        "tipo": tipo,
                        "pagina": pagina,
                        "erro": f"{type(exc).__name__}: {exc}",
                    },
                )
                return False

            if total_count is None:
                total_count = resposta.get("total_count")

            html = resposta.get("results_html") or ""
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint="specials",
                    identificador=f"{tipo}-pagina-{pagina:03d}",
                    payload=html,
                )
            )

            if "data-ds-appid" not in html:
                # Pagina vazia - acabaram as ofertas (ultima pagina real).
                break

            inicio += RESULTADOS_POR_PAGINA
            if total_count is not None and inicio >= total_count:
                break
        else:
            # Esgotou `MAX_PAGINAS` sem parar naturalmente - trava de
            # seguranca acionada, nao o fim real da lista.
            self.logger.warning(
                "MAX_PAGINAS atingido antes do fim natural da varredura",
                extra={"tipo": tipo, "paginas": MAX_PAGINAS},
            )
            return False

        logger.info(
            "varredura de um tipo concluida",
            extra={"tipo": tipo, "total_count_steam": total_count},
        )
        return True

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoOfertasSteam:
        linhas = []
        tags: dict[int, str] = {}
        for registro in registros:
            if registro.fonte != self.fonte:
                continue
            if registro.endpoint == "tags":
                tags = parse_dicionario_tags(registro.payload)
                continue
            # `identificador` e "<tipo>-pagina-NNN"; paginas gravadas antes
            # da separacao por tipo (2026-09-16) nao tem prefixo e sao lidas
            # como jogo, que era o que a varredura unica majoritariamente
            # trazia - reprocessar raw antigo nao pode quebrar.
            tipo = registro.identificador.split("-", 1)[0]
            if tipo not in CATEGORIA_POR_TIPO:
                tipo = TIPO_JOGO
            linhas.extend(parse_pagina(registro.payload, tipo=tipo))
        return ResultadoOfertasSteam(linhas=linhas, tags=tags, completa=self._completa)

    def load(self, dados: ResultadoOfertasSteam) -> int:
        resumo = carregar(
            dados.linhas,
            completa=dados.completa,
            tags=dados.tags,
            settings=self.settings,
        )
        return resumo.promocoes_abertas + resumo.promocoes_atualizadas

    def close(self) -> None:
        self.client.close()
