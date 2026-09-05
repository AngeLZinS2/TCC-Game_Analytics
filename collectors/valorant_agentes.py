"""Agentes do VALORANT, da valorant-api.com.

O banco ja tinha VALORANT: 87 equipes e 87 confrontos na agenda, vindos da
Liquipedia. O que faltava era o elenco - `dim_personagem` tinha 127 herois de
Dota e zero agentes. O efeito disso no assistente era pior do que uma lacuna:
perguntado sobre Valorant ele respondia que "Valorant nao esta no nosso banco",
o que e falso, e caia no conhecimento geral.

**Por que nao a API oficial da Riot.** A `val/content/v1/contents` responde 401
sem chave, exige aprovacao de projeto e, mesmo com chave, devolve so nomes e
ids localizados - nao devolve funcao nem habilidade. A valorant-api.com e um
espelho comunitario do proprio cliente do jogo (le os assets do jogo), sem
chave, com os campos que a pergunta usa: funcao e habilidades, em portugues.

**O que esta fonte NAO responde.** Ela e um CATALOGO, nao um placar. Nao ha
taxa de escolha, taxa de vitoria nem nada que sustente "o melhor agente do meta
atual" - isso exigiria dado de partida competitiva de Valorant, que esta
plataforma nao coleta. Quem monta o contexto tem que dizer isso: o elenco
responde "quem existe e o que faz", nunca "quem esta forte agora".
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from typing import Any, Sequence

import requests

from collectors import opgg_mcp
from collectors.base import BaseCollector, RawRecord
from config import get_settings

logger = logging.getLogger(__name__)

URL_AGENTES = "https://valorant-api.com/v1/agents"

#: A ficha oficial do agente no site da Riot. O `__NEXT_DATA__` dela traz o
#: clipe curto de cada habilidade - o mesmo `.mp4` que o op.gg mostra, servido
#: do CDN da propria Riot (`cmsassets.rgpub.io`). A valorant-api.com nao tem
#: esse video; so o icone.
#:
#: pt-br de proposito: o casamento com a valorant-api (tambem em pt-BR) e por
#: NOME de habilidade, e "Blaze" em ingles nao bate com "Chama" em portugues.
URL_FICHA_RIOT = "https://playvalorant.com/pt-br/agents/{slug}/"

#: O codigo do jogo em `dim_jogo`, semeado pela migration das wikis.
JOGO = "valorant"

#: Idioma dos nomes de funcao e habilidade. A pergunta chega em portugues
#: ("quais agentes sao duelistas"), entao o contexto tambem tem que estar.
IDIOMA = "pt-BR"

#: Pausa entre as fichas da Riot. Sao 29 paginas por rodada (semanal); 0.5s
#: de folga e cortesia com um site que nao publica limite.
PAUSA_FICHA_RIOT = 0.5


def _chave(texto: str) -> str:
    """Nome normalizado para casar entre fontes: sem acento, sem simbolo, minusculo."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def _chave_habilidade(titulo: str) -> str:
    """Como `_chave`, tirando o que a ficha da Riot poe alem do nome:

    - o prefixo de tecla: "Q - Predador Explosivo" -> "Predador Explosivo"
    - o parentetico:      "Enseada (Fumaca de Enseada)" -> "Enseada"
    - o segundo nome:     "Nebulosa/Dissipar" -> "Nebulosa"

    A valorant-api entrega so o nome limpo, entao normalizar os dois lados
    assim faz a maioria casar; o resto cai no `in` de `_casar_video`.
    """
    t = re.sub(r"^\s*[CQEX]\s*[-–—]\s*", "", titulo, flags=re.I)
    t = re.sub(r"\(.*?\)", "", t)
    t = t.split("/")[0]
    return _chave(t)


def _casar_video(nome_habilidade: str, videos: dict[str, str]) -> str | None:
    """O clipe da habilidade, casando por nome com tolerancia.

    `videos` ja vem com as chaves passadas por `_chave_habilidade`. Tenta o
    casamento exato; se falhar, aceita um que contenha ou esteja contido no
    outro (cobre "Forma Astral" x "Forma Astral Divisao Cosmica").
    """
    alvo = _chave(nome_habilidade)
    if alvo in videos:
        return videos[alvo]
    for chave, url in videos.items():
        if len(alvo) >= 4 and (alvo in chave or chave in alvo):
            return url
    return None


def _slug_riot(nome: str) -> str:
    """O nome do agente na URL da Riot. "KAY/O" -> "kay-o"."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


class AgentesValorantCollector(BaseCollector[list[dict[str, Any]]]):
    """Elenco completo de agentes jogaveis, com funcao e habilidades."""

    fonte = "valorant_agentes"

    def collect(self) -> list[RawRecord]:
        elenco = self._elenco()
        registros = [elenco]

        # Os clipes de habilidade, da ficha oficial da Riot. Falha aqui nao
        # leva o resto: a tela funciona so com icone + texto.
        try:
            agentes_brutos = (elenco.payload or {}).get("data") or []
            registros.append(self._videos_habilidades(agentes_brutos))
        except Exception as exc:  # noqa: BLE001 - uma fonte a menos, nao a rodada
            self.logger.warning("videos de habilidade falharam", extra={"erro": str(exc)})

        # A estatistica e de outra fonte e pode faltar sem levar o elenco
        # junto: sem ela a tela mostra quem existe e diz que falta o numero,
        # que e melhor do que nao mostrar agente nenhum.
        if get_settings().opgg_enabled:
            try:
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint="valorant_list_agent_statistics",
                        identificador="estatisticas",
                        payload=opgg_mcp.estatisticas_agentes_valorant(),
                    )
                )
            except opgg_mcp.OpggIndisponivel as exc:
                self.logger.warning("estatistica do opgg falhou", extra={"erro": str(exc)})

            # Estatistica por mapa - o recorte que da profundidade ao detalhe do
            # agente. Um mapa que falhar nao leva os outros; a lista geral acima
            # ja garante o minimo.
            try:
                mapas = opgg_mcp.mapas_valorant()
            except opgg_mcp.OpggIndisponivel as exc:
                mapas = []
                self.logger.warning("lista de mapas falhou", extra={"erro": str(exc)})

            for mapa in mapas:
                try:
                    registros.append(
                        RawRecord(
                            fonte=self.fonte,
                            endpoint="valorant_list_agent_statistics",
                            identificador=f"mapa:{mapa['nome']}",
                            payload=opgg_mcp.estatisticas_agentes_valorant(mapa["id"]),
                        )
                    )
                except opgg_mcp.OpggIndisponivel as exc:
                    self.logger.warning(
                        "estatistica por mapa falhou",
                        extra={"mapa": mapa["nome"], "erro": str(exc)},
                    )

        return registros

    def _elenco(self) -> RawRecord:
        settings = get_settings()
        resposta = requests.get(
            URL_AGENTES,
            # `isPlayableCharacter` tira o duplicado do Sova que a API mantem
            # por compatibilidade - sem ele o elenco vem com um agente a mais
            # que nao existe no jogo.
            params={"isPlayableCharacter": "true", "language": IDIOMA},
            timeout=settings.http_timeout_seconds,
            headers={"Accept": "application/json"},
        )
        resposta.raise_for_status()
        return RawRecord(
            fonte=self.fonte,
            endpoint=URL_AGENTES,
            identificador="agentes",
            payload=resposta.json(),
        )

    def _videos_habilidades(self, agentes: list[dict[str, Any]]) -> RawRecord:
        """O clipe de cada habilidade, da ficha oficial de cada agente na Riot.

        Uma pagina por agente. Uma que falhe (agente novo sem ficha, mudanca de
        layout) so deixa aquele agente sem video - a tela ja mostra o icone e o
        texto sem ele.
        """
        settings = get_settings()
        por_agente: dict[str, dict[str, str]] = {}

        for bruto in agentes:
            nome = bruto.get("displayName")
            if not isinstance(nome, str):
                continue
            try:
                resposta = requests.get(
                    URL_FICHA_RIOT.format(slug=_slug_riot(nome)),
                    timeout=settings.http_timeout_seconds,
                    headers={"User-Agent": "Mozilla/5.0 (GamingAnalyticsTCC)"},
                )
                resposta.raise_for_status()
                videos = _extrair_videos(resposta.text)
                if videos:
                    por_agente[_chave(nome)] = videos
            except (requests.RequestException, ValueError) as exc:
                self.logger.warning(
                    "ficha da riot falhou", extra={"agente": nome, "erro": str(exc)}
                )
            time.sleep(PAUSA_FICHA_RIOT)

        return RawRecord(
            fonte=self.fonte,
            endpoint="playvalorant.com",
            identificador="videos_habilidades",
            payload=por_agente,
        )

    def parse(self, registros: Sequence[RawRecord]) -> list[dict[str, Any]]:
        agentes: dict[str, dict[str, Any]] = {}
        estatisticas: dict[str, dict[str, Any]] = {}
        # id_externo -> [{mapa, partidas, vitorias, winrate, pick_rate, metricas}]
        por_mapa: dict[str, list[dict[str, Any]]] = {}
        # nome_normalizado -> {nome_habilidade_norm: url_video}
        videos: dict[str, dict[str, str]] = {}

        for registro in registros:
            if registro.identificador == "videos_habilidades":
                if isinstance(registro.payload, dict):
                    videos = registro.payload
                continue

            if registro.identificador == "estatisticas":
                for linha in registro.payload or []:
                    if isinstance(linha, dict) and linha.get("id_externo"):
                        estatisticas[linha["id_externo"]] = linha
                continue

            if registro.identificador.startswith("mapa:"):
                mapa = registro.identificador[len("mapa:") :]
                for linha in registro.payload or []:
                    if isinstance(linha, dict) and linha.get("id_externo"):
                        por_mapa.setdefault(linha["id_externo"], []).append(
                            {**linha, "mapa": mapa}
                        )
                continue

            payload = registro.payload
            if not isinstance(payload, dict):
                continue
            for bruto in payload.get("data") or []:
                agente = _normalizar_agente(bruto)
                if agente is not None:
                    agentes[agente["id_externo"]] = agente

        # O casamento e por uuid: o OP.GG usa o MESMO identificador de agente
        # que a valorant-api.com, entao nao ha heuristica de nome no meio.
        for id_externo, agente in agentes.items():
            numeros = estatisticas.get(id_externo)
            if numeros:
                agente["partidas"] = numeros.get("partidas")
                agente["vitorias"] = numeros.get("vitorias")
                agente["metricas"] = numeros.get("metricas") or {}
            agente["por_mapa"] = por_mapa.get(id_externo, [])

            # O video casa por NOME de habilidade (a Riot titula em maiuscula,
            # a valorant-api em capitalizado) - o uuid nao serve aqui porque a
            # ficha da Riot nao expoe id de habilidade.
            do_agente = videos.get(_chave(agente["nome"]), {})
            for hab in agente["metadados"]["habilidades"]:
                hab["video"] = _casar_video(hab["nome"] or "", do_agente)

        return list(agentes.values())

    def load(self, dados: list[dict[str, Any]]) -> int:
        from etl.load_valorant import carregar_agentes, carregar_estatisticas

        carregados = carregar_agentes(dados)
        carregar_estatisticas(dados)
        return carregados


def _extrair_videos(html: str) -> dict[str, str]:
    """`{nome_habilidade_norm: url_mp4}` da ficha oficial de um agente.

    O site da Riot e Next.js: o `__NEXT_DATA__` traz a pagina como uma lista de
    "blades", e a de habilidades e a do tipo `iconTab` com header "ABILITIES".
    Cada grupo dela tem `content.title` (nome da habilidade) e
    `content.media.sources[0].src` (o clipe). Se a Riot mudar essa forma, o
    resultado vem vazio - a tela cai no icone, nao quebra.
    """
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.S
    )
    if not m:
        return {}
    try:
        dados = json.loads(m.group(1))
    except ValueError:
        return {}

    blades = (
        dados.get("props", {})
        .get("pageProps", {})
        .get("page", {})
        .get("blades", [])
    )
    videos: dict[str, str] = {}
    for blade in blades:
        # A blade de habilidades e a unica `iconTab` da ficha. Nao filtro pelo
        # texto do header ("Special Abilities" / "Habilidades Especiais" muda
        # com o idioma) - o formato e o mesmo.
        if not isinstance(blade, dict) or blade.get("type") != "iconTab":
            continue
        for grupo in blade.get("groups") or []:
            conteudo = grupo.get("content") if isinstance(grupo, dict) else None
            if not isinstance(conteudo, dict):
                continue
            titulo = conteudo.get("title")
            fontes = (conteudo.get("media") or {}).get("sources") or []
            src = fontes[0].get("src") if fontes and isinstance(fontes[0], dict) else None
            if isinstance(titulo, str) and isinstance(src, str) and ".mp4" in src:
                videos[_chave_habilidade(titulo)] = src
    return videos


def _normalizar_agente(bruto: Any) -> dict[str, Any] | None:
    """Um agente da API no formato de `dim_personagem`, ou `None` se incompleto.

    O `uuid` vira `id_externo` por ser o que a fonte usa como chave - o mesmo
    criterio do heroi da OpenDota. Nome muda de traducao, uuid nao.
    """
    if not isinstance(bruto, dict):
        return None

    uuid = bruto.get("uuid")
    nome = bruto.get("displayName")
    if not isinstance(uuid, str) or not isinstance(nome, str) or not nome.strip():
        return None

    papel = (bruto.get("role") or {}).get("displayName")

    habilidades = [
        {
            "slot": h.get("slot"),
            "nome": h.get("displayName"),
            "descricao": h.get("description"),
            "icone": h.get("displayIcon"),
            # Preenchido no `parse`, casando por nome com a ficha da Riot.
            "video": None,
        }
        for h in (bruto.get("abilities") or [])
        if isinstance(h, dict) and h.get("displayName")
    ]

    # `developerName` e o nome interno do agente no cliente ("Clay" e o Raze,
    # "Pandemic" e a Viper). Mesmo papel do `npc_dota_hero_*` no Dota: e por
    # ele que se casa com dado de outra fonte quando o nome exibido diverge.
    return {
        "id_externo": uuid,
        "nome": nome.strip()[:64],
        "nome_interno": (bruto.get("developerName") or None),
        "papel": papel.strip()[:32] if isinstance(papel, str) and papel.strip() else None,
        # O que NAO muda - vai para `dim_personagem.metadados`. E a parte
        # estatica da tela de detalhe: lore, retratos e as habilidades.
        "metadados": {
            "descricao": bruto.get("description"),
            "icone": bruto.get("displayIcon"),
            "retrato": bruto.get("fullPortrait"),
            "fundo": bruto.get("background"),
            "habilidades": habilidades,
        },
        # Compat: o assistente ainda le esta lista plana.
        "habilidades": [h["nome"] for h in habilidades if h["nome"]],
    }
