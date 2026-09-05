"""Campeoes de League of Legends: desempenho por rota e guia de build, via OP.GG.

LoL nao aparecia na tela de personagens por um motivo simples: `dim_personagem`
tinha 127 herois de Dota, 29 agentes de Valorant e ZERO campeoes. Nunca foram
coletados. O seletor esconde jogo sem personagem, entao ele nem era oferecido.

**A rota e o eixo da estatistica aqui, e isso e proprio do jogo.** Um campeao
nao tem "um" desempenho: Pantheon no topo e Pantheon no meio sao dois conjuntos
de numeros diferentes, e o proprio OP.GG publica assim - uma tabela por rota.
Este coletor busca as cinco e guarda, para cada campeao, a rota em que ele mais
e jogado (`role_rate` mais alto) junto dos numeros dessa rota. E a leitura que
responde "como esse campeao esta?" sem inventar uma media entre rotas que
ninguem joga.

**As metricas sao as de League, nao as de outro jogo.** Taxa de banimento nao
existe em Dota nem em Valorant e e das leituras mais fortes do meta - um
campeao com 40% de ban esta forte mesmo com winrate mediano, porque quase
metade das partidas nao deixa ele ser escolhido. `tier` e o rank que o OP.GG
publica (1 e o melhor), e vem junto por ser o resumo que a comunidade usa.

**O guia de build.** Alem de "como esse campeao esta?", a tela de detalhe
responde "como jogar?": item inicial, botas, nucleo, ordem de subir a
habilidade, feiticos e as runas - tudo do meta atual, na rota principal do
campeao. Vem de `lol_get_champion_analysis`, uma chamada por campeao.

**Por que a rodada NAO busca os 170 de uma vez.** O `lol_get_champion_analysis`
tem um teto por janela (algo horario): passado ~110 numa rajada, o OP.GG passa
a devolver, em vez de erro, um payload de forma certa e arrays vazios. Entao a
rodada busca so os campeoes SEM guia ou com guia velho (`GUIA_VALIDADE_DIAS`);
o resto e pulado. Com a carga que MESCLA o `metadados` (ver
`etl/load_personagens`), a cobertura so cresce: em duas ou tres rodadas
semanais os 170 estao cobertos, e dai cada rodada so renova os que venceram.

Os combos que o OP.GG traz sao demonstracoes em video no YouTube, conteudo da
comunidade - entram como link, com a origem marcada, nao embutidos.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

import requests
from sqlalchemy import select

from collectors import opgg_mcp
from collectors.base import BaseCollector, RawRecord
from config import get_settings
from db.models import DimJogo, DimPersonagem
from db.session import session_scope

logger = logging.getLogger(__name__)

#: O codigo do jogo em `dim_jogo`, semeado pela migration das wikis.
JOGO = "leagueoflegends"

#: As rotas, e como cada uma se chama em portugues. A chave e o que a
#: ferramenta aceita; o valor vira `dim_personagem.papel`, do mesmo jeito que
#: "Duelista" e "Sentinela" no Valorant.
ROTAS: dict[str, str] = {
    "TOP": "Topo",
    "JUNGLE": "Selva",
    "MID": "Meio",
    "ADC": "Atirador",
    "SUPPORT": "Suporte",
}

FERRAMENTA_ELENCO = "lol_list_champions"
FERRAMENTA_ROTA = "lol_list_lane_meta_champions"
FERRAMENTA_GUIA = "lol_get_champion_analysis"

#: A rota da meta (chave de `ROTAS`) para o enum que o guia aceita.
POSICAO_GUIA: dict[str, str] = {
    "TOP": "top",
    "JUNGLE": "jungle",
    "MID": "mid",
    "ADC": "adc",
    "SUPPORT": "support",
}

# O guia pede a resposta INTEIRA (`desired_output_fields: []`). O filtro de
# campos do OP.GG e intermitente sob carga - devolve um payload degradado (so
# `counters_meta`) e diz que os campos "nao casaram", com a dica de mandar
# array vazio para a resposta completa. A completa tem ~5 KB e o nosso parser
# navega por chave, entao os ramos extras (counters, synergies, trends) so sao
# ignorados.

#: Folga entre as chamadas do guia, alem do rate limit padrao do cliente.
PAUSA_GUIA = 1.5

#: Um guia mais velho que isto e recoletado; mais novo, e pulado. Mantem o
#: numero de chamadas por rodada baixo (so os que faltam ou venceram) e o dado
#: fresco o bastante - build de campeao muda a cada patch, ~2 semanas.
GUIA_VALIDADE_DIAS = 12

#: Os feiticos de invocador. O OP.GG devolve so o id numerico - a Riot nunca
#: muda esses ids, entao a tabela e fixa e em pt-BR.
FEITICOS_LOL: dict[int, str] = {
    1: "Purificar",
    3: "Exaustao",
    4: "Flash",
    6: "Fantasma",
    7: "Curar",
    11: "Punir",
    12: "Teleporte",
    13: "Clarividencia",
    14: "Chamas",
    21: "Barreira",
    32: "Marca",
    39: "Marca",
}

#: O idioma dos nomes. "Nunu & Willump" em pt_BR, "Nunu & Willump" em en_US -
#: varios sao iguais, mas alguns mudam, e a tela e em portugues.
IDIOMA = "pt_BR"

#: Data Dragon - o dado estatico OFICIAL da Riot para LoL: lore, retrato,
#: passiva e as quatro habilidades com icone e texto, tudo em pt_BR. E a CDN
#: da propria Riot (o mesmo papel da valorant-api.com para os agentes); nao ha
#: limite de taxa e cabe numa chamada so (`championFull.json`, ~2 MB).
DDRAGON_VERSOES = "https://ddragon.leagueoflegends.com/api/versions.json"
DDRAGON_CAMPEOES = (
    "https://ddragon.leagueoflegends.com/cdn/{versao}/data/pt_BR/championFull.json"
)
DDRAGON_ITENS = (
    "https://ddragon.leagueoflegends.com/cdn/{versao}/data/pt_BR/item.json"
)
DDRAGON_IMG = "https://ddragon.leagueoflegends.com/cdn/{versao}/img"


def _juntar_nome(nome: str) -> str:
    """Chave de casamento entre o elenco (pt-BR) e as tabelas de rota (en).

    `lol_list_champions` responde "Nunu e Willump"; `lol_list_lane_meta_champions`
    responde "Nunu & Willump". Minusculo, `&` vira `e` e espaco colapsa - o
    resto dos ~170 nomes ja bate.
    """
    import re

    return re.sub(r"\s+", " ", nome.lower().replace("&", "e")).strip()


class CampeoesLolCollector(BaseCollector[list[dict[str, Any]]]):
    """Elenco de campeoes e o desempenho na rota principal de cada um."""

    fonte = "lol_campeoes"

    def collect(self) -> list[RawRecord]:
        registros: list[RawRecord] = []

        # Sem tratamento: falhar aqui derruba a rodada, e e o certo - sem o
        # elenco nao ha personagem a cadastrar, e as cinco chamadas de rota
        # seriam trabalho para jogar fora.
        registros.append(
            RawRecord(
                fonte=self.fonte,
                endpoint=FERRAMENTA_ELENCO,
                identificador="elenco",
                payload=opgg_mcp.chamar_ferramenta(
                    FERRAMENTA_ELENCO, {"lang": IDIOMA, "desired_output_fields": []}
                ),
            )
        )

        for rota in ROTAS:
            try:
                registros.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint=FERRAMENTA_ROTA,
                        identificador=f"rota:{rota}",
                        payload=opgg_mcp.chamar_ferramenta(
                            FERRAMENTA_ROTA,
                            {"position": rota, "desired_output_fields": []},
                        ),
                    )
                )
            except opgg_mcp.OpggIndisponivel as exc:
                # Uma rota fora do ar nao leva as outras quatro: o campeao que
                # so aparece nela fica sem numero, os demais seguem.
                self.logger.warning(
                    "rota do opgg falhou", extra={"rota": rota, "erro": str(exc)}
                )

        # O dado estatico da Riot. Falha aqui nao leva o resto: a tela ja
        # mostra nome, retrato e numeros sem a lore e as habilidades.
        try:
            registros.append(self._estatico())
        except requests.RequestException as exc:
            self.logger.warning("data dragon falhou", extra={"erro": str(exc)})

        registros.extend(self._guias(registros))
        return registros

    def _estatico(self) -> RawRecord:
        settings = get_settings()
        versao = requests.get(
            DDRAGON_VERSOES, timeout=settings.http_timeout_seconds
        ).json()[0]
        campeoes = requests.get(
            DDRAGON_CAMPEOES.format(versao=versao),
            timeout=settings.http_timeout_seconds,
        ).json()
        # `item.json` (~1 MB) so para o icone de cada item do guia - o OP.GG da
        # o nome ja em pt-BR, mas nao o icone.
        try:
            itens = requests.get(
                DDRAGON_ITENS.format(versao=versao),
                timeout=settings.http_timeout_seconds,
            ).json()
        except requests.RequestException:
            itens = {}
        return RawRecord(
            fonte=self.fonte,
            endpoint="ddragon",
            identificador="estatico",
            payload={
                "versao": versao,
                "data": campeoes.get("data", {}),
                "itens": itens.get("data", {}),
            },
        )

    def _guias(self, registros: Sequence[RawRecord]) -> list[RawRecord]:
        """Uma chamada de `lol_get_champion_analysis` por campeao SEM guia fresco.

        A rota principal sai das tabelas de rota ja coletadas (maior
        `role_rate`). Campeao que ja tem guia com menos de `GUIA_VALIDADE_DIAS`
        e pulado - isso segura o numero de chamadas dentro do teto por janela do
        OP.GG. Cada chamada e isolada.
        """
        frescos = self._guias_frescos()
        # `key` interno da Riot ("MonkeyKing", "LeeSin") - o `champion` do guia
        # aceita nome, key ou UPPER_SNAKE, mas a key e a forma canonica.
        chave: dict[str, str] = {}
        for registro in registros:
            if registro.identificador != "elenco" or not isinstance(
                registro.payload, str
            ):
                continue
            for bruto in opgg_mcp.analisar_notacao_compacta(
                registro.payload, "Champion"
            ):
                if isinstance(bruto.get("name"), str) and isinstance(
                    bruto.get("key"), str
                ):
                    chave[_juntar_nome(bruto["name"])] = bruto["key"]

        posicao: dict[str, str] = {}  # nome do campeao -> enum de posicao
        melhor_taxa: dict[str, float] = {}
        for registro in registros:
            if not registro.identificador.startswith("rota:"):
                continue
            rota = registro.identificador.removeprefix("rota:")
            if not isinstance(registro.payload, str):
                continue
            for bruto in opgg_mcp.analisar_notacao_compacta(
                registro.payload, rota.capitalize()
            ):
                nome = bruto.get("champion")
                taxa = bruto.get("role_rate") or 0
                if not isinstance(nome, str):
                    continue
                juncao = _juntar_nome(nome)
                if juncao not in melhor_taxa or taxa > melhor_taxa[juncao]:
                    melhor_taxa[juncao] = taxa
                    posicao[juncao] = POSICAO_GUIA.get(rota, "mid")

        pendentes = [
            (juncao, pos)
            for juncao, pos in sorted(posicao.items())
            if juncao not in frescos
        ]
        self.logger.info(
            "guias a coletar",
            extra={"pendentes": len(pendentes), "frescos": len(frescos)},
        )

        guias: list[RawRecord] = []
        for i, (juncao, pos) in enumerate(pendentes):
            texto = self._guia_do_opgg(chave.get(juncao, juncao), pos, juncao)
            if texto is not None:
                guias.append(
                    RawRecord(
                        fonte=self.fonte,
                        endpoint=FERRAMENTA_GUIA,
                        identificador=f"guia:{juncao}",
                        payload=texto,
                    )
                )
            if i + 1 < len(pendentes):
                time.sleep(PAUSA_GUIA)
        return guias

    def _guias_frescos(self) -> set[str]:
        """Os campeoes cujo guia foi coletado ha menos de `GUIA_VALIDADE_DIAS`.

        Chave no formato de `_juntar_nome`, para casar com o laco de `_guias`.
        Falha de banco devolve conjunto vazio - a rodada tenta todos, e o teto
        do OP.GG corta o excesso.
        """
        limite = (
            datetime.now(timezone.utc) - timedelta(days=GUIA_VALIDADE_DIAS)
        ).date().isoformat()
        try:
            with session_scope() as sessao:
                linhas = sessao.execute(
                    select(DimPersonagem.nome, DimPersonagem.metadados)
                    .join(DimJogo, DimJogo.id_jogo == DimPersonagem.id_jogo)
                    .where(
                        DimJogo.codigo == JOGO,
                        DimPersonagem.metadados.has_key("guia"),
                    )
                ).all()
        except Exception as exc:  # noqa: BLE001 - sem banco, recoleta tudo
            self.logger.warning("nao consultou guias frescos", extra={"erro": str(exc)})
            return set()

        frescos: set[str] = set()
        for nome, metadados in linhas:
            guia = (metadados or {}).get("guia") or {}
            if str(guia.get("atualizado_em") or "") >= limite:
                frescos.add(_juntar_nome(nome))
        return frescos

    def _guia_do_opgg(self, champion: str, pos: str, rotulo: str) -> str | None:
        """Uma chamada do guia, com uma nova tentativa para a resposta vazia.

        Sob carga o OP.GG devolve, em vez de erro, um payload com a forma certa
        e todos os arrays vazios (`is_rip: true`, `damage_type: "UNKNOWN"`).
        Testado um a um, o mesmo campeao responde cheio - e questao de ritmo, nao
        de o dado nao existir. Uma pausa longa e uma segunda tentativa recuperam
        parte; o resto fica para a proxima rodada, e a carga MESCLA o `metadados`
        (ver `etl/load_personagens`), entao a cobertura so cresce.
        """
        for tentativa in range(2):
            try:
                texto = opgg_mcp.chamar_ferramenta(
                    FERRAMENTA_GUIA,
                    {
                        "champion": champion,
                        "position": pos,
                        "game_mode": "ranked",
                        "lang": IDIOMA,
                        "desired_output_fields": [],
                    },
                )
            except opgg_mcp.OpggIndisponivel as exc:
                self.logger.warning(
                    "guia do opgg falhou",
                    extra={"campeao": rotulo, "erro": str(exc)},
                )
                return None

            arvore = opgg_mcp.analisar_objeto_compacto(texto)
            if _montar_guia_lol(arvore, None, {}) is not None:
                return texto
            if tentativa == 0:
                time.sleep(8)

        self.logger.warning("guia do opgg veio vazio", extra={"campeao": rotulo})
        return None

    def parse(self, registros: Sequence[RawRecord]) -> list[dict[str, Any]]:
        elenco: dict[str, dict[str, Any]] = {}
        melhor_rota: dict[str, dict[str, Any]] = {}
        # nome -> [{rota, play, win, ...}] - todas as rotas onde o campeao joga
        por_rota: dict[str, list[dict[str, Any]]] = {}
        # key do campeao (nome_interno) -> metadados
        estatico: dict[str, dict[str, Any]] = {}
        # id do item (str) -> url do icone, do `item.json` do Data Dragon
        icone_item: dict[str, str] = {}
        # nome do campeao -> arvore do guia (build, runas, skills, combos)
        guia_bruto: dict[str, Any] = {}

        for registro in registros:
            if registro.identificador == "estatico" and isinstance(registro.payload, dict):
                estatico = _metadados_ddragon(registro.payload)
                icone_item = _icones_item_ddragon(registro.payload)
                continue

            texto = registro.payload
            if not isinstance(texto, str):
                continue

            if registro.identificador.startswith("guia:"):
                juncao = registro.identificador[len("guia:") :]
                arvore = opgg_mcp.analisar_objeto_compacto(texto)
                if isinstance(arvore, dict):
                    guia_bruto[juncao] = arvore
                continue

            if registro.identificador == "elenco":
                for bruto in opgg_mcp.analisar_notacao_compacta(texto, "Champion"):
                    nome = bruto.get("name")
                    chave = bruto.get("key")
                    if not isinstance(nome, str) or not isinstance(chave, str):
                        continue
                    identificador = bruto.get("champion_id")
                    if not isinstance(identificador, int):
                        continue

                    # A fonte devolve 236 linhas para 173 campeoes: 63 sao
                    # variantes de modo de jogo, com o MESMO nome exibido e id
                    # 60000+ ("Jade_Annie", 60001). Ficar com a ultima punha
                    # `Jade_Annie` no lugar da Annie. O canonico e o de MENOR
                    # id - criterio que nao depende do prefixo do momento.
                    anterior = elenco.get(nome)
                    if anterior is not None and int(anterior["id_externo"]) <= identificador:
                        continue

                    elenco[nome] = {
                        # `champion_id` e a chave estavel da Riot; `key` e o
                        # nome interno ("MonkeyKing" e o Wukong), mesmo papel
                        # do `npc_dota_hero_*`.
                        "id_externo": str(identificador),
                        "nome": nome[:64],
                        "nome_interno": chave[:64],
                    }
                continue

            rota = registro.identificador.removeprefix("rota:")
            # A classe da notacao e o nome da rota capitalizado: `Mid`, `Top`.
            for bruto in opgg_mcp.analisar_notacao_compacta(texto, rota.capitalize()):
                nome = bruto.get("champion")
                if not isinstance(nome, str):
                    continue
                por_rota.setdefault(nome, []).append({**bruto, "rota": rota})
                atual = melhor_rota.get(nome)
                # A rota principal e a de maior `role_rate` - a proporcao das
                # partidas do campeao que acontecem nela. Media entre rotas
                # descreveria um campeao que ninguem joga.
                if atual is None or (bruto.get("role_rate") or 0) > (
                    atual.get("role_rate") or 0
                ):
                    melhor_rota[nome] = {**bruto, "rota": rota}

        campeoes: list[dict[str, Any]] = []
        for nome, campeao in elenco.items():
            numeros = melhor_rota.get(nome)
            if numeros is not None:
                campeao["papel"] = ROTAS.get(numeros["rota"], numeros["rota"])
                campeao["partidas"] = numeros.get("play")
                campeao["vitorias"] = numeros.get("win")
                campeao["metricas"] = _metricas(numeros)

            # Uma linha por rota onde o campeao aparece - o "por mapa" do LoL.
            # Pantheon topo e Pantheon meio sao dois conjuntos, e essa e a
            # leitura que a tela de detalhe mostra.
            campeao["por_mapa"] = [
                {
                    "mapa": ROTAS.get(r["rota"], r["rota"]),
                    "partidas": r.get("play"),
                    "vitorias": r.get("win"),
                    "metricas": _metricas(r),
                }
                for r in sorted(
                    por_rota.get(nome, []),
                    key=lambda x: x.get("role_rate") or 0,
                    reverse=True,
                )
            ]

            metadados = estatico.get(campeao["nome_interno"])
            guia = _montar_guia_lol(
                guia_bruto.get(_juntar_nome(nome)),
                rota_pt=campeao.get("papel"),
                icone_item=icone_item,
            )
            if guia is not None:
                metadados = {**(metadados or {}), "guia": guia}
            campeao["metadados"] = metadados
            campeoes.append(campeao)

        return campeoes

    def load(self, dados: list[dict[str, Any]]) -> int:
        from etl.load_lol import carregar_campeoes

        return carregar_campeoes(dados)


def _limpar_html(texto: str | None) -> str | None:
    """Tira as tags do texto de habilidade do Data Dragon.

    O texto vem com `<br>`, `<font color=...>` e afins - a tela mostra em
    paragrafo simples, entao a marcacao so atrapalha.
    """
    import re

    if not isinstance(texto, str):
        return None
    limpo = re.sub(r"<br\s*/?>", " ", texto)
    limpo = re.sub(r"<[^>]+>", "", limpo)
    # `%i:OnHit%` e afins - placeholders de template do Data Dragon no campo
    # `description` (o `tooltip` tem ainda mais).
    limpo = re.sub(r"\{\{[^}]+\}\}|%[a-z]?:?[A-Za-z]+%", "…", limpo)
    return re.sub(r"\s+", " ", limpo).strip() or None


def _metadados_ddragon(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`{key_do_campeao: metadados}` a partir do `championFull.json`.

    Mesmo formato do `metadados` do agente de Valorant: descricao, retrato,
    icone e as habilidades (passiva + Q/W/E/R) com nome, texto e icone. E por
    isso a tela de detalhe funciona igual nos dois - ela le `metadados`, nao
    sabe de que jogo e.
    """
    versao = payload.get("versao", "")
    img = DDRAGON_IMG.format(versao=versao)
    saida: dict[str, dict[str, Any]] = {}

    for key, campeao in (payload.get("data") or {}).items():
        if not isinstance(campeao, dict):
            continue

        habilidades: list[dict[str, Any]] = []
        passiva = campeao.get("passive") or {}
        if passiva.get("name"):
            habilidades.append(
                {
                    "slot": "Passiva",
                    "nome": passiva["name"],
                    "descricao": _limpar_html(passiva.get("description")),
                    "icone": f"{img}/passive/{passiva['image']['full']}"
                    if passiva.get("image", {}).get("full")
                    else None,
                    "video": None,
                }
            )
        for slot, feitico in zip(("Q", "W", "E", "R"), campeao.get("spells") or []):
            if not feitico.get("name"):
                continue
            habilidades.append(
                {
                    "slot": slot,
                    "nome": feitico["name"],
                    "descricao": _limpar_html(feitico.get("description")),
                    "icone": f"{img}/spell/{feitico['image']['full']}"
                    if feitico.get("image", {}).get("full")
                    else None,
                    "video": None,
                }
            )

        saida[key] = {
            "descricao": campeao.get("lore") or campeao.get("blurb"),
            "icone": f"{img}/champion/{campeao['image']['full']}"
            if campeao.get("image", {}).get("full")
            else None,
            # O "retrato" grande: a splash de carregamento, no mesmo caminho de
            # sempre da Riot.
            "retrato": (
                "https://ddragon.leagueoflegends.com/cdn/img/champion/loading/"
                f"{key}_0.jpg"
            ),
            "fundo": (
                "https://ddragon.leagueoflegends.com/cdn/img/champion/splash/"
                f"{key}_0.jpg"
            ),
            "habilidades": habilidades,
        }
    return saida


def _icones_item_ddragon(payload: dict[str, Any]) -> dict[str, str]:
    """`{id_do_item: url_do_icone}` a partir do `item.json`.

    Nomes se repetem (o mesmo item tem uma versao de Arena com id 220000+); o
    OP.GG devolve o id junto do nome, entao o casamento e por id e nao precisa
    desambiguar.
    """
    versao = payload.get("versao", "")
    img = DDRAGON_IMG.format(versao=versao)
    saida: dict[str, str] = {}
    for id_item, item in (payload.get("itens") or {}).items():
        cheio = (item or {}).get("image", {}).get("full")
        if cheio:
            saida[str(id_item)] = f"{img}/item/{cheio}"
    return saida


def _grupo_itens(
    titulo: str, no: Any, icone_item: dict[str, str]
) -> dict[str, Any] | None:
    """Um estagio da build (`{titulo, itens, nota}`) de um no do guia do OP.GG.

    `no` tem `ids`, `ids_names` e `pick_rate`. Os dois primeiros andam juntos;
    quando so um vem, o nome manda e o icone fica sem.
    """
    if not isinstance(no, dict):
        return None
    nomes = no.get("ids_names") or []
    ids = no.get("ids") or []
    itens: list[dict[str, Any]] = []
    for i, nome in enumerate(nomes):
        id_item = ids[i] if i < len(ids) else None
        itens.append(
            {"nome": nome, "icone": icone_item.get(str(id_item)) if id_item else None}
        )
    if not itens:
        return None
    taxa = no.get("pick_rate")
    nota = (
        f"{round(taxa * 100)}% escolhem"
        if isinstance(taxa, (int, float)) and taxa
        else None
    )
    return {"titulo": titulo, "itens": itens, "nota": nota}


def _montar_guia_lol(
    arvore: Any, rota_pt: str | None, icone_item: dict[str, str]
) -> dict[str, Any] | None:
    """O guia de build do campeao, da arvore de `lol_get_champion_analysis`.

    Devolve `None` quando a arvore nao veio ou nao tem nem build nem skills -
    o campeao fica so com os numeros. Os combos sao links de video do YouTube
    (conteudo da comunidade que o OP.GG agrega); entram com a origem marcada.
    """
    if not isinstance(arvore, dict):
        return None
    dados = arvore.get("data")
    if not isinstance(dados, dict):
        return None

    grupos = [
        g
        for g in (
            _grupo_itens("Itens iniciais", dados.get("starter_items"), icone_item),
            _grupo_itens("Botas", dados.get("boots"), icone_item),
            _grupo_itens("Itens nucleo", dados.get("core_items"), icone_item),
        )
        if g
    ]
    finais: list[dict[str, Any]] = []
    for opcao in dados.get("last_items") or []:
        if not isinstance(opcao, dict):
            continue
        nome = (opcao.get("ids_names") or [None])[0]
        id_item = (opcao.get("ids") or [None])[0]
        if nome:
            finais.append(
                {
                    "nome": nome,
                    "icone": icone_item.get(str(id_item)) if id_item else None,
                }
            )
    if finais:
        grupos.append(
            {"titulo": "Opcoes de item final", "itens": finais, "nota": None}
        )

    feiticos = [
        FEITICOS_LOL[i]
        for i in (dados.get("summoner_spells") or {}).get("ids", []) or []
        if i in FEITICOS_LOL
    ]

    def _pagina(nome_pagina: Any, escolhas: Any) -> dict[str, Any] | None:
        if not isinstance(nome_pagina, str):
            return None
        return {
            "pagina": nome_pagina,
            "escolhas": [e for e in (escolhas or []) if isinstance(e, str)],
        }

    runas = dados.get("runes") or {}
    skills = dados.get("skills") or {}
    maestria = dados.get("skill_masteries") or {}
    combos = [
        {"nome": c.get("name"), "url": c.get("video_url")}
        for c in dados.get("skill_combos") or []
        if isinstance(c, dict) and c.get("name") and c.get("video_url")
    ]

    ordem = [s for s in skills.get("order", []) or [] if isinstance(s, str)]
    prioridade = [s for s in maestria.get("ids", []) or [] if isinstance(s, str)]

    tem_algo = grupos or feiticos or runas or ordem or combos
    if not tem_algo:
        return None

    return {
        "fonte": "OP.GG",
        "rota": rota_pt,
        "atualizado_em": date.today().isoformat(),
        "grupos": grupos,
        "feiticos": feiticos,
        "runa_primaria": _pagina(
            runas.get("primary_page_name"), runas.get("primary_rune_names")
        ),
        "runa_secundaria": _pagina(
            runas.get("secondary_page_name"), runas.get("secondary_rune_names")
        ),
        "ordem_habilidades": ordem,
        "prioridade_habilidades": prioridade,
        "combos": combos,
        "nota_habilidades": None,
    }


def _fracao_para_percentual(valor: Any) -> float | None:
    """O OP.GG publica taxa como fracao (0.51). A tela mostra em pontos."""
    if not isinstance(valor, (int, float)):
        return None
    return round(100 * float(valor), 1)


def _metricas(bruto: dict[str, Any]) -> dict[str, float | None]:
    return {
        "pick_rate": _fracao_para_percentual(bruto.get("pick_rate")),
        # Nao existe em Dota nem em Valorant, e e das leituras mais fortes do
        # meta de League: um campeao com 40% de ban esta forte mesmo com
        # winrate mediano - quase metade das partidas nao deixa escolhe-lo.
        "ban_rate": _fracao_para_percentual(bruto.get("ban_rate")),
        "role_rate": _fracao_para_percentual(bruto.get("role_rate")),
        "kda": bruto.get("kda") if isinstance(bruto.get("kda"), (int, float)) else None,
        # 1 e o melhor. A tela sabe disso por `maior_melhor=False` no perfil.
        "tier": bruto.get("tier") if isinstance(bruto.get("tier"), int) else None,
    }
