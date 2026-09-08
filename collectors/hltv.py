"""Partidas de Counter-Strike por vir, raspadas do hltv.org.

O HLTV é o placar de CS do cenário — o que o vlr.gg é para Valorant. A agenda
de CS já vinha do ticker da Liquipedia, mas de forma esparsa (a wiki lista só
os torneios que alguém mantém); o `hltv.org/matches` tem TODAS as partidas
marcadas, com id estável e horário em UTC no atributo.

Lê só `/matches` (a lista de próximas + ao vivo; resultados ficam em
`/matches/results`, fora do escopo deste coletor — a agenda é o que a tela
"Próximas partidas" mostra).

**Markup.** `<div class="match-wrapper" data-match-id data-event-id live team1
team2>` com `<div class="match-time" data-unix>`, `<div class="match-meta">bo3`
e dois `<div class="match-teamname">`. O `data-unix` é ms UTC — não precisa
adivinhar fuso como no vlr.gg.

**Torneio.** O card não traz o nome do evento; ele está no slug da URL
(`/matches/ID/furia-vs-gamerlegion-fissure-playground-3`). Tira-se o prefixo
dos dois times e o que sobra é o evento.

**Cloudflare.** O HLTV bloqueia cliente HTTP comum por TLS fingerprint — um
GET do `requests` (ou do `curl` puro) leva 403, independente dos headers. O
`curl_cffi` com `impersonate="chrome"` reproduz o ClientHello do Chrome e
passa. É uma requisição por rodada (5 min); se um dia parar de passar, o
coletor loga e a Liquipedia continua cobrindo CS.
"""

from __future__ import annotations

import html
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from curl_cffi import requests as cffi_requests

from collectors.base import BaseCollector, RawRecord
from config import get_settings

logger = logging.getLogger(__name__)

JOGO = "counterstrike"
URL_MATCHES = "https://www.hltv.org/matches"

_WRAPPER = re.compile(
    r'<div class="match-wrapper[^"]*"[^>]*data-match-id="(?P<id>\d+)"[^>]*'
    r'live="(?P<live>true|false)"[^>]*>(?P<corpo>.*?)'
    r'(?=<div class="match-wrapper|<div class="matches-list-column|</section)',
    re.S,
)
_HREF = re.compile(r'href="/matches/(\d+)/([a-z0-9-]+)"')
_UNIX = re.compile(r'match-time[^>]*data-unix="(\d+)"')
_META = re.compile(r'match-meta[^"]*">\s*([^<]+?)\s*<')
_TEAMNAME = re.compile(r'match-teamname[^>]*>\s*([^<]+?)\s*<')

_TBD = {"tbd", "", "-"}


@dataclass
class PartidaHltv:
    id_externo: str
    equipe_a_nome: str
    equipe_b_nome: str
    inicio_previsto: datetime
    torneio: str | None
    formato: str | None
    # A agenda do HLTV é só o futuro; resultado sempre nulo aqui.
    vitoria_a: bool | None = None
    placar_a: int | None = None
    placar_b: int | None = None


@dataclass
class ResultadoHltv:
    partidas: list[PartidaHltv] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.partidas)


def _slug(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


#: Siglas que ficam em caixa alta no nome do torneio (o `.title()` estragaria).
_SIGLAS = {"esl", "cct", "blast", "iem", "pgl", "esea", "epl", "wesg", "cs", "eu", "na", "sa", "lan"}


def _torneio_do_slug(slug: str, nome_a: str, nome_b: str) -> str | None:
    """`furia-vs-gamerlegion-fissure-playground-3` -> `Fissure Playground 3`."""
    resto = slug
    prefixo = f"{_slug(nome_a)}-vs-{_slug(nome_b)}-"
    if resto.startswith(prefixo):
        resto = resto[len(prefixo) :]
    else:
        # times com caractere fora do padrão: corta no `-vs-<algo>-`
        m = re.match(r"[a-z0-9-]+?-vs-[a-z0-9]+-(.+)", resto)
        resto = m.group(1) if m else ""
    palavras = [
        p.upper() if p in _SIGLAS else p.capitalize()
        for p in resto.split("-")
        if p
    ]
    return " ".join(palavras) or None


def _formato(bruto: str | None) -> str | None:
    if not bruto:
        return None
    m = re.search(r"bo\s*(\d)", bruto, re.I)
    return f"Bo{m.group(1)}" if m else None


def _parse(pagina_html: str) -> list[PartidaHltv]:
    vistos: set[str] = set()
    partidas: list[PartidaHltv] = []

    for w in _WRAPPER.finditer(pagina_html):
        mid = w.group("id")
        if mid in vistos:
            continue
        corpo = w.group("corpo")

        nomes = [html.unescape(n).strip() for n in _TEAMNAME.findall(corpo)[:2]]
        if len(nomes) < 2 or any(n.lower() in _TBD for n in nomes):
            continue
        nome_a, nome_b = nomes

        unix = _UNIX.search(corpo)
        if not unix:
            continue
        inicio = datetime.fromtimestamp(int(unix.group(1)) / 1000, tz=timezone.utc)

        href = _HREF.search(corpo)
        torneio = _torneio_do_slug(href.group(2), nome_a, nome_b) if href else None
        meta = _META.search(corpo)

        vistos.add(mid)
        partidas.append(
            PartidaHltv(
                id_externo=f"hltv:{mid}",
                equipe_a_nome=nome_a[:120],
                equipe_b_nome=nome_b[:120],
                inicio_previsto=inicio,
                torneio=torneio,
                formato=_formato(meta.group(1) if meta else None),
            )
        )

    return partidas


class HltvCollector(BaseCollector[ResultadoHltv]):
    """Próximas partidas de CS do hltv.org."""

    fonte = "hltv"

    def collect(self) -> list[RawRecord]:
        settings = get_settings()
        timeout = settings.http_timeout_seconds

        corpo: str | None = None
        for tentativa in range(3):
            try:
                resp = cffi_requests.get(
                    URL_MATCHES, impersonate="chrome", timeout=timeout
                )
                resp.raise_for_status()
                corpo = resp.text
                break
            except Exception as exc:  # noqa: BLE001 - loga e tenta de novo
                self.logger.warning(
                    "hltv/matches falhou",
                    extra={"tentativa": tentativa + 1, "erro": str(exc)},
                )
                time.sleep(2 * (tentativa + 1))

        if corpo is None:
            raise RuntimeError("hltv.org/matches não respondeu em 3 tentativas")

        return [
            RawRecord(
                fonte=self.fonte,
                endpoint="/matches",
                identificador="upcoming",
                payload=corpo,
            )
        ]

    def parse(self, registros: Sequence[RawRecord]) -> ResultadoHltv:
        partidas: list[PartidaHltv] = []
        for registro in registros:
            if isinstance(registro.payload, str):
                partidas.extend(_parse(registro.payload))
        return ResultadoHltv(partidas=partidas)

    def load(self, dados: ResultadoHltv) -> int:
        from etl.load_hltv import carregar

        return carregar(dados)
