"""O registro de wikis da Liquipedia que o projeto conhece.

A Liquipedia publica ~80 wikis. Este registro tem 73, e a diferenca nao e
arbitraria: saiu de uma varredura em que cada wiki foi perguntada sobre as duas
coisas que o nosso pipeline consome.

* `Liquipedia:Matches` existe? -> da para coletar agenda
* `Category:Teams` tem membros? -> da para coletar equipes

O resultado, medido:

| situacao | quantas | exemplos |
|---|---|---|
| agenda e times | 64 | dota2, counterstrike, valorant, leagueoflegends |
| so times | 7 | fighters, starcraft2, smash, formula1, brawlhalla |
| so agenda | 2 | sideswipe, wildcard |
| nenhum | 1 | illuvium (fora do registro) |

Os sete "so times" tem uma explicacao comum: sao competicoes INDIVIDUAIS. Em
Smash, StarCraft, Fighting Games e Formula 1 quem se enfrenta e pessoa, nao
equipe, e a wiki organiza o calendario de outro jeito. A ausencia da pagina nao
e falha - e o formato do esporte aparecendo no esquema.

Ficam de fora `commons`, `hub`, `lab`, `esports` e `dota2gamearchive`: sao
wikis meta, internas ou de arquivo. Entrariam como linhas em `dim_jogo` sem
nunca receber uma partida.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ARQUIVO_REGISTRO = (
    Path(__file__).resolve().parent.parent
    / "collectors"
    / "seeds"
    / "liquipedia_wikis.json"
)


#: Genero de esporte -> o substantivo que a serie de um confronto conta.
#:
#: A Liquipedia guarda um placar por confronto (`agenda_partida.placar_a/b`),
#: mas o que ele MEDE muda com o jogo: mapas num FPS, jogos num card game,
#: pontos no xadrez. `battle-royale` e `corrida` nao tem serie 1-contra-1 -
#: sao colocacao numa lobby - entao nao ha unidade e o fator de saldo nem
#: aparece.
UNIDADE_PLACAR: dict[str, str | None] = {
    "fps": "mapas",
    "moba": "jogos",
    "cartas": "jogos",
    "autobattler": "jogos",
    "estrategia": "jogos",
    "luta": "jogos",
    "esporte": "jogos",
    "arena": "jogos",
    "tabuleiro": "pontos",
    "battle-royale": None,
    "corrida": None,
    "outro": None,
}


@dataclass(frozen=True, slots=True)
class Wiki:
    """Uma wiki da Liquipedia e o que da para coletar dela."""

    codigo: str
    nome: str
    #: fps, moba, cartas, estrategia, luta, battle-royale, esporte, corrida,
    #: tabuleiro, arena, autobattler, outro. Ver `UNIDADE_PLACAR`.
    genero: str
    #: `Liquipedia:Matches` existe nesta wiki.
    agenda: bool
    #: `Category:Teams` tem membros nesta wiki.
    times: bool

    @property
    def url_api(self) -> str:
        return f"https://liquipedia.net/{self.codigo}/api.php"

    @property
    def unidade_placar(self) -> str | None:
        """Como se chama o que o placar de um confronto conta neste jogo."""
        return UNIDADE_PLACAR.get(self.genero)


@lru_cache(maxsize=1)
def registro() -> tuple[Wiki, ...]:
    """As wikis conhecidas, na ordem do arquivo."""
    dados = json.loads(ARQUIVO_REGISTRO.read_text(encoding="utf-8"))
    return tuple(
        Wiki(
            codigo=item["codigo"],
            nome=item["nome"],
            genero=item.get("genero", "outro"),
            agenda=bool(item.get("agenda")),
            times=bool(item.get("times")),
        )
        for item in dados
    )


def por_codigo(codigo: str) -> Wiki | None:
    return next((w for w in registro() if w.codigo == codigo), None)


def unidade_placar(codigo: str) -> str | None:
    """A unidade do placar de um confronto do jogo - `None` se nao se aplica.

    "mapas" para FPS, "jogos" para card game / MOBA, "pontos" para xadrez.
    Jogo desconhecido ou de colocacao (battle royale, corrida) devolve `None`.
    """
    wiki = por_codigo(codigo)
    return wiki.unidade_placar if wiki is not None else None


def com_agenda() -> tuple[Wiki, ...]:
    return tuple(w for w in registro() if w.agenda)


def com_times() -> tuple[Wiki, ...]:
    return tuple(w for w in registro() if w.times)


def codigos() -> tuple[str, ...]:
    return tuple(w.codigo for w in registro())
