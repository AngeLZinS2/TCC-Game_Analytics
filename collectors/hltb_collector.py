"""Coletor de tempo estimado pra zerar via HowLongToBeat.

O HLTB nao tem API oficial, nao pede chave e nao tem SDK - o que existe e a
busca de texto do proprio site (`/api/search/site`), que qualquer navegador
chama sem login. Ela e protegida por um token de sessao de curta duracao:

    1. GET  /api/search/site/init?t=<epoch_ms>  -> {token, hpKey, hpVal}
    2. POST /api/search/site                    -> {data: [<candidatos>]}
       headers: x-auth-token, x-hp-key, x-hp-val (do passo 1)
       corpo:   {..., "<hpKey>": "<hpVal>"}      (o mesmo par, de novo, no corpo)

O token vale para varias buscas seguidas (o proprio site so renova quando uma
busca devolve 403) - por isso `_auth` e memorizado por execucao do coletor,
nao refeito a cada jogo.

**Fragilidade assumida.** Isto e engenharia reversa de um endpoint que a
Valve^H^H a equipe do HLTB pode reformular a qualquer momento (ja mudou de
`/api/s/` para `/api/search/site` entre versoes) - se um dia comecar a falhar
sistematicamente, o primeiro lugar a olhar e `_BASE_URL + _BUSCA_PATH` e o
formato do corpo em `_corpo_busca`. Ate la, uma falha de UM jogo (`falhas`)
nao derruba a rodada inteira, e o app funciona identico sem esse dado -
"tempo pra zerar" e um extra, nunca um requisito.

Casamento por NOME (o HLTB nao conhece Steam appid) e responsabilidade do
`etl.transform_hltb`, nao daqui - este modulo so fala com a rede.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Sequence

import requests
from sqlalchemy import select

from collectors.base import BaseCollector, RawRecord
from collectors.http_client import RateLimitedClient
from config import Settings, get_settings
from db.models import DimJogoSteam
from db.session import session_scope
from etl.load_hltb import carregar
from etl.transform_hltb import ENDPOINT_BUSCA, FONTE, ResultadoHltb, transformar

logger = logging.getLogger(__name__)

_BASE_URL = "https://howlongtobeat.com"
_BUSCA_PATH = "/api/search/site"
_INIT_PATH = "/api/search/site/init"

#: User-Agent de navegador comum - o endpoint rejeita clientes obviamente
#: automatizados (sem User-Agent, ou o default do `requests`).
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


@dataclass(slots=True)
class _Sessao:
    token: str
    hp_key: str
    hp_val: str


#: Simbolos que a Steam guarda no nome ("Apex Legends™") mas que a busca do
#: HLTB nao reconhece - "Legends™" (colado, sem espaco) nao bate com
#: "Legends" nenhum, e a busca inteira volta vazia (`count: 0`).
_SIMBOLOS_MARCA = str.maketrans("", "", "™®©")


def _normalizar_busca(nome: str) -> str:
    return " ".join(nome.translate(_SIMBOLOS_MARCA).split())


def jogos_para_tempo(limite: int | None = None) -> list[tuple[int, str]]:
    """`(app_id, nome)` dos jogos que ainda NUNCA foram buscados no HLTB.

    Diferente do ITAD (que cacheia so o id e busca preco de novo toda
    rodada), aqui o id E os tempos saem da MESMA chamada de busca - uma vez
    resolvido (`hltb_id` preenchido, mesmo que `""` de "nao achei") nao ha o
    que atualizar buscando de novo. So `hltb_id IS NULL` volta a entrar.
    """
    with session_scope() as sessao:
        consulta = (
            select(DimJogoSteam.app_id, DimJogoSteam.nome)
            .where(DimJogoSteam.hltb_id.is_(None))
            .order_by(DimJogoSteam.app_id)
        )
        if limite:
            consulta = consulta.limit(limite)
        return [(linha.app_id, linha.nome) for linha in sessao.execute(consulta)]


def _corpo_busca(nome_jogo: str, sessao: _Sessao) -> dict[str, Any]:
    corpo: dict[str, Any] = {
        "searchType": "games",
        "searchTerms": nome_jogo.split(),
        "searchPage": 1,
        "size": 20,
        "searchOptions": {
            "games": {
                "userId": 0,
                "platform": "",
                "sortCategory": "popular",
                "rangeCategory": "main",
                "rangeTime": {"min": 0, "max": 0},
                "gameplay": {"perspective": "", "flow": "", "genre": "", "difficulty": ""},
                "rangeYear": {"max": "", "min": ""},
                "modifier": "",
            },
            "users": {"sortCategory": "postcount"},
            "lists": {"sortCategory": "follows"},
            "filter": "",
            "sort": 0,
            "randomizer": 0,
        },
        "useCache": True,
    }
    # O site manda o mesmo par (hpKey -> hpVal) de novo, agora como campo do
    # corpo - alem do header. Parece redundante; sem os dois, 403.
    corpo[sessao.hp_key] = sessao.hp_val
    return corpo


class HltbCollector(BaseCollector[ResultadoHltb]):
    fonte = FONTE

    def __init__(
        self,
        raw_storage: Any,
        settings: Settings | None = None,
        limite: int | None = None,
    ) -> None:
        super().__init__(raw_storage)
        self.settings = settings or get_settings()
        self.limite = limite
        self.falhas = 0

        self.client = RateLimitedClient(
            nome="hltb",
            intervalo_minimo=self.settings.hltb_rate_limit_seconds,
            max_retries=self.settings.http_max_retries,
            timeout=self.settings.http_timeout_seconds,
            user_agent=_USER_AGENT,
        )

    def _autenticar(self) -> _Sessao | None:
        try:
            payload = self.client.get_json(
                f"{_BASE_URL}{_INIT_PATH}",
                params={"t": int(time.time() * 1000)},
                headers={"Referer": _BASE_URL},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "init do hltb falhou - endpoint pode ter mudado",
                extra={"erro": f"{type(exc).__name__}: {exc}"},
            )
            return None
        if not isinstance(payload, dict) or not payload.get("token"):
            return None
        return _Sessao(
            token=str(payload["token"]),
            hp_key=str(payload.get("hpKey")),
            hp_val=str(payload.get("hpVal")),
        )

    def _buscar(self, nome_jogo: str, sessao: _Sessao) -> tuple[Any, _Sessao]:
        """Busca um jogo; renova a sessao e refaz UMA vez se ela expirou (403)."""
        headers = {
            "content-type": "application/json",
            "x-auth-token": sessao.token,
            "x-hp-key": sessao.hp_key,
            "x-hp-val": sessao.hp_val,
            "Referer": _BASE_URL,
            "Origin": _BASE_URL,
        }
        try:
            return (
                self.client.post_json(
                    f"{_BASE_URL}{_BUSCA_PATH}",
                    json=_corpo_busca(nome_jogo, sessao),
                    headers=headers,
                ),
                sessao,
            )
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 403:
                raise
            nova = self._autenticar()
            if nova is None:
                raise
            headers.update(
                {"x-auth-token": nova.token, "x-hp-key": nova.hp_key, "x-hp-val": nova.hp_val}
            )
            return (
                self.client.post_json(
                    f"{_BASE_URL}{_BUSCA_PATH}",
                    json=_corpo_busca(nome_jogo, nova),
                    headers=headers,
                ),
                nova,
            )

    def collect(self) -> list[RawRecord]:
        alvos = jogos_para_tempo(self.limite)
        if not alvos:
            logger.info("nenhum jogo pendente de tempo no hltb")
            return []

        sessao = self._autenticar()
        if sessao is None:
            logger.warning("nao foi possivel autenticar no hltb - pulando a rodada")
            self.falhas += len(alvos)
            return []

        registros: list[RawRecord] = []
        for app_id, nome in alvos:
            consulta = _normalizar_busca(nome)
            try:
                resultado, sessao = self._buscar(consulta, sessao)
            except Exception as exc:  # noqa: BLE001 - um jogo nao derruba os outros
                self.falhas += 1
                logger.warning(
                    "busca de um jogo no hltb falhou",
                    extra={"app_id": app_id, "erro": f"{type(exc).__name__}: {exc}"},
                )
                continue
            registros.append(
                RawRecord(
                    fonte=self.fonte,
                    endpoint=ENDPOINT_BUSCA,
                    identificador=str(app_id),
                    payload={"app_id": app_id, "consulta": consulta, "resultado": resultado},
                )
            )

        return registros

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoHltb:
        return transformar(registros)

    def load(self, resultado: ResultadoHltb) -> int:
        return carregar(resultado)

    def close(self) -> None:
        self.client.close()
