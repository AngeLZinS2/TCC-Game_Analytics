"""Wikitexto das paginas de equipe da Liquipedia -> modelo validado.

**Por que o wikitexto e nao o HTML.** O outro parser da Liquipedia
(`transform_liquipedia.py`) le HTML renderizado, porque a pagina da agenda e
montada por Lua a partir da base interna deles e o wikitexto dela tem 234
caracteres - so uma invocacao de modulo, sem dado nenhum. Para EQUIPES o
caminho e o inverso: a pagina e escrita a mao, e o `{{Infobox team}}` esta no
fonte. Ler o fonte evita depender de classe de CSS, que muda quando eles mexem
no tema e leva o parser junto.

**O que isto resolve.** A agenda chega com nome de exibicao, e casar nome com
nome e frageil - foi por isso que `load_liquipedia.py` recusa casamento difuso.
O infobox traz `|teamid=`, que e o MESMO identificador que a OpenDota usa em
`radiant_team.team_id`. Com ele o vinculo deixa de ser semelhanca de texto e
vira igualdade de inteiro.

**Sobre a extracao ser um parser e nao um regex.** A primeira tentativa foi
`\\|\\s*disbanded\\s*=\\s*([^\\n|]*)`, e ela devolveu `}}` para uma equipe ativa:
o campo vazio faz o padrao engolir o fechamento do template. Valores de infobox
tambem contem `[[links]]` e `{{templates}}` aninhados, com `|` dentro, que um
regex nao sabe ignorar. Dai o caminhamento por profundidade abaixo.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

FONTE = "liquipedia"
ENDPOINT_EQUIPES = "equipes"

#: A categoria que lista as paginas de equipe da wiki de Dota 2.
CATEGORIA_EQUIPES = "Category:Teams"

#: Regioes como a Liquipedia escreve, normalizadas para uma forma so.
#:
#: O mesmo campo aparece como `cis`, `CIS` e `Commonwealth of Independent
#: States` em paginas diferentes - sao editores diferentes ao longo de dez anos.
#: Sem esta tabela, um agrupamento por regiao mostraria a mesma regiao em tres
#: linhas.
REGIOES = {
    "cis": "CIS",
    "commonwealth of independent states": "CIS",
    "europe": "Europe",
    "eu": "Europe",
    "north america": "North America",
    "na": "North America",
    "south america": "South America",
    "sa": "South America",
    "southeast asia": "Southeast Asia",
    "sea": "Southeast Asia",
    "china": "China",
    "cn": "China",
    "oceania": "Oceania",
    "oce": "Oceania",
    "africa": "Africa",
    "middle east": "Middle East",
    "south asia": "South Asia",
}


class EquipeWiki(BaseModel):
    """Uma equipe como a Liquipedia a descreve."""

    pagina: str
    nome: str
    #: O `teamid` do infobox. E a chave do vinculo com a OpenDota, e por isso
    #: uma equipe sem ele nao serve ao proposito deste modulo.
    id_externo: int
    regiao: str | None = None
    pais: str | None = None
    ativa: bool = True
    criada_em: date | None = None


class ResultadoEquipes(BaseModel):
    equipes: list[EquipeWiki] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.equipes)


def campos_do_template(texto: str, nome: str) -> dict[str, str]:
    """Os parametros de um template do wikitexto, por nome.

    Caminha caractere a caractere contando profundidade de `{{}}` e `[[]]`, e so
    corta em `|` que esteja no nivel de cima. E o que faz `|location=[[Serbia]]`
    e `|sponsor={{Link|x|y}}` sobreviverem inteiros em vez de virarem dois
    campos partidos ao meio.

    Devolve dicionario vazio quando o template nao esta no texto - pagina de
    equipe sem infobox existe (redirecionamento, esboco), e nao e erro.
    """
    inicio = re.search(r"\{\{\s*" + re.escape(nome) + r"\b", texto, re.IGNORECASE)
    if inicio is None:
        return {}

    i = inicio.end()
    profundidade_chaves = 0
    profundidade_colchetes = 0
    partes: list[str] = []
    atual: list[str] = []

    while i < len(texto):
        par = texto[i : i + 2]

        if par == "{{":
            profundidade_chaves += 1
            atual.append(par)
            i += 2
            continue
        if par == "}}":
            if profundidade_chaves == 0:
                break  # fecha o nosso template
            profundidade_chaves -= 1
            atual.append(par)
            i += 2
            continue
        if par == "[[":
            profundidade_colchetes += 1
            atual.append(par)
            i += 2
            continue
        if par == "]]":
            profundidade_colchetes = max(0, profundidade_colchetes - 1)
            atual.append(par)
            i += 2
            continue

        caractere = texto[i]
        if (
            caractere == "|"
            and profundidade_chaves == 0
            and profundidade_colchetes == 0
        ):
            partes.append("".join(atual))
            atual = []
        else:
            atual.append(caractere)
        i += 1

    partes.append("".join(atual))

    campos: dict[str, str] = {}
    for parte in partes:
        if "=" not in parte:
            continue
        chave, _, valor = parte.partition("=")
        campos[chave.strip().lower()] = valor.strip()
    return campos


def _limpar(valor: str) -> str:
    """Tira marcacao de wiki de um valor curto de infobox."""
    valor = re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", valor)  # [[a|b]] -> b
    valor = re.sub(r"\{\{[^}]*\}\}", "", valor)  # templates residuais
    valor = re.sub(r"<[^>]+>", "", valor)  # tags HTML soltas
    return re.sub(r"\s+", " ", valor).strip()


def _regiao(valor: str) -> str | None:
    limpo = _limpar(valor)
    if not limpo or limpo == "-":
        return None
    return REGIOES.get(limpo.lower(), limpo)


def _data(valor: str) -> date | None:
    """A data do infobox, quando ela e uma data de verdade.

    A wiki aceita `2015-12-06`, mas tambem `2014-??-??` e `2013-05-??` - o
    editor sabia o ano e nao o dia. Completar o `??` com `01` inventaria
    precisao que a fonte nao tem, entao o parcial vira `None`.
    """
    limpo = _limpar(valor)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", limpo):
        return None
    try:
        return date.fromisoformat(limpo)
    except ValueError:
        return None


def parse_equipe(pagina: str, wikitexto: str) -> EquipeWiki | None:
    """Uma pagina de equipe -> `EquipeWiki`, ou `None` se ela nao serve.

    Descarta quem nao tem `teamid`: sem ele nao ha vinculo com as partidas, e
    uma linha so com nome e regiao nao responde nenhuma pergunta do projeto.
    """
    campos = campos_do_template(wikitexto, "Infobox team")
    if not campos:
        return None

    bruto_id = _limpar(campos.get("teamid", ""))
    if not bruto_id.isdigit():
        return None

    return EquipeWiki(
        pagina=pagina,
        nome=_limpar(campos.get("name", "")) or pagina,
        id_externo=int(bruto_id),
        regiao=_regiao(campos.get("region", "")),
        pais=_limpar(campos.get("location", "")) or None,
        # Campo vazio = em atividade. E a convencao da propria wiki.
        ativa=not _limpar(campos.get("disbanded", "")),
        criada_em=_data(campos.get("created", "")),
    )


def transformar(payload: object) -> ResultadoEquipes:
    """Normaliza a resposta de `action=query&prop=revisions` em lote.

    O payload e o JSON inteiro da MediaWiki; cada pagina traz a secao 0 do
    wikitexto. Paginas sem revisao (apagadas entre o indice e a leitura) e sem
    infobox saem em silencio - sao esperadas, nao falhas.
    """
    if not isinstance(payload, dict):
        return ResultadoEquipes()

    paginas = (payload.get("query") or {}).get("pages") or {}
    if not isinstance(paginas, dict):
        return ResultadoEquipes()

    equipes: list[EquipeWiki] = []
    vistos: set[int] = set()

    for pagina in paginas.values():
        if not isinstance(pagina, dict):
            continue
        titulo = pagina.get("title")
        revisoes = pagina.get("revisions") or []
        if not titulo or not revisoes:
            continue

        conteudo = ((revisoes[0].get("slots") or {}).get("main") or {}).get("*")
        if not isinstance(conteudo, str):
            continue

        equipe = parse_equipe(titulo, conteudo)
        if equipe is None:
            continue

        # A wiki tem redirecionamentos e paginas de organizacao que apontam para
        # o mesmo teamid. Duas linhas com o mesmo id quebrariam o upsert.
        if equipe.id_externo in vistos:
            continue
        vistos.add(equipe.id_externo)
        equipes.append(equipe)

    return ResultadoEquipes(equipes=equipes)
