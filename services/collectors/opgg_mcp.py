"""Cliente do servidor MCP do OP.GG - chamado por Python, nunca pelo modelo.

O OP.GG publica 29 ferramentas sobre League of Legends, TFT e VALORANT
(estatistica de agente, tier de campeao por rota, composicao por mapa, perfil
de invocador). E a fonte que faltava: ate aqui o projeto tinha partida so de
Dota 2, e "qual o melhor agente do Valorant" nao tinha resposta com dado.

**Por que o modelo nao fala com este servidor.**

MCP existe para dar ferramentas a um modelo de linguagem. Ligar assim seria o
caminho natural - e seria repetir o erro que definiu a arquitetura deste
projeto. Os modelos gratuitos do OpenRouter ignoram `tools`, e ignoram ate
`tool_choice: "required"`: perguntados quantos jogos da Steam eram monitorados,
respondiam "20.285" com toda a confianca, sem chamar nada. O numero era 12.

Mas MCP e so JSON-RPC sobre HTTP. Nada obriga o cliente a ser um modelo. Este
modulo chama `tools/call` de forma deterministica, com os argumentos que o
Python escolheu, e o resultado vira bloco de contexto - do mesmo jeito que
`steam_loja` e `itad_loja`. O modelo recebe numeros ja buscados; ele nao
escolhe o que buscar, nao sabe que este servidor existe e nao pode inventar uma
chamada.

**Sobre a sessao.** O transporte "streamable HTTP" exige um aperto de mao:
`initialize` devolve um `mcp-session-id` no cabecalho, e toda chamada seguinte
precisa dele. A sessao e reaproveitada entre chamadas do mesmo processo e
refeita sozinha quando o servidor a expira - o custo dela e de tres viagens,
e pagar isso por pergunta seria desperdicio.

**Sobre o limite de taxa.** O OP.GG nao documenta nenhum. Isso nao e permissao:
e a mesma situacao da Liquipedia antes da politica escrita, e o projeto trata
igual - um intervalo minimo entre chamadas, configuravel, conservador por
padrao. O servidor e gratuito e mantido por terceiros.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any

import requests

from config import get_settings

logger = logging.getLogger(__name__)

#: O aperto de mao e a versao do protocolo que o servidor anunciou na conexao
#: de teste. Fixa de proposito: subir sem verificar quebraria em silencio.
VERSAO_PROTOCOLO = "2025-06-18"

_CABECALHOS = {
    "Content-Type": "application/json",
    # Os dois: o servidor responde JSON puro em algumas ferramentas e
    # `text/event-stream` em outras, e recusa quem so aceita um dos dois.
    "Accept": "application/json, text/event-stream",
}

#: Sessao viva do processo. O lock existe porque o agendador roda tarefas em
#: sequencia mas a API responde perguntas em paralelo (FastAPI usa threadpool):
#: duas perguntas simultaneas fariam dois `initialize` e um sobrescreveria o
#: outro no meio do uso.
_sessao: str | None = None
_trava = threading.Lock()
_ultimo_pedido = 0.0


class OpggIndisponivel(RuntimeError):
    """O servidor nao respondeu ou recusou. Quem chama segue sem o bloco."""


def _esperar_a_vez() -> None:
    """Segura a chamada ate o intervalo minimo desde a anterior."""
    global _ultimo_pedido
    intervalo = get_settings().opgg_rate_limit_seconds
    espera = intervalo - (time.monotonic() - _ultimo_pedido)
    if espera > 0:
        time.sleep(espera)
    _ultimo_pedido = time.monotonic()


def _postar(corpo: dict[str, Any], sessao: str | None) -> requests.Response:
    settings = get_settings()
    cabecalhos = dict(_CABECALHOS)
    if sessao:
        cabecalhos["mcp-session-id"] = sessao
    _esperar_a_vez()
    return requests.post(
        settings.opgg_mcp_url,
        headers=cabecalhos,
        json=corpo,
        timeout=settings.http_timeout_seconds,
    )


def _abrir_sessao() -> str:
    """Aperto de mao. Devolve o id da sessao."""
    resposta = _postar(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": VERSAO_PROTOCOLO,
                "capabilities": {},
                "clientInfo": {"name": "playdb", "version": "0.1"},
            },
        },
        sessao=None,
    )
    resposta.raise_for_status()

    sessao = resposta.headers.get("mcp-session-id")
    if not sessao:
        raise OpggIndisponivel("servidor nao devolveu mcp-session-id")

    # Sem esta notificacao o servidor considera o aperto de mao incompleto e
    # recusa `tools/call`. Nao tem `id`: e notificacao, nao pedido.
    _postar({"jsonrpc": "2.0", "method": "notifications/initialized"}, sessao)
    return sessao


def _corpo_json(resposta: requests.Response) -> dict[str, Any]:
    """O JSON-RPC de dentro da resposta, seja ela JSON puro ou SSE.

    Em `text/event-stream` o payload vem em linhas `data: {...}`; a ultima e a
    resposta final. Tratar as duas formas aqui evita que cada chamador
    descubra sozinho qual ferramenta responde em qual formato.
    """
    texto = resposta.text
    if "data: " in texto:
        blocos = [
            linha[len("data: ") :]
            for linha in texto.splitlines()
            if linha.startswith("data: ")
        ]
        if not blocos:
            raise OpggIndisponivel("fluxo SSE sem linha de dados")
        texto = blocos[-1]
    try:
        return json.loads(texto)
    except ValueError as exc:
        raise OpggIndisponivel(f"resposta nao era JSON: {texto[:120]}") from exc


def chamar_ferramenta(nome: str, argumentos: dict[str, Any]) -> Any:
    """Executa uma ferramenta e devolve o conteudo ja desempacotado.

    Levanta `OpggIndisponivel` em qualquer falha - de rede, de protocolo ou
    logica (o MCP sinaliza erro de ferramenta com `isError`, dentro de uma
    resposta HTTP 200, entao olhar so o status esconderia a falha).
    """
    global _sessao

    with _trava:
        if _sessao is None:
            _sessao = _abrir_sessao()
        sessao = _sessao

    pedido = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": nome, "arguments": argumentos},
    }

    try:
        resposta = _postar(pedido, sessao)
        # 400/404 aqui e sessao expirada, nao ferramenta errada: refaz o aperto
        # de mao uma vez. Sem isso, um processo de vida longa (a API) pararia
        # de responder sobre Valorant depois de horas ociosas.
        if resposta.status_code in (400, 404):
            with _trava:
                _sessao = _abrir_sessao()
                sessao = _sessao
            resposta = _postar(pedido, sessao)
        resposta.raise_for_status()
    except requests.RequestException as exc:
        raise OpggIndisponivel(f"{type(exc).__name__}: {exc}") from exc

    corpo = _corpo_json(resposta)
    if "error" in corpo:
        raise OpggIndisponivel(str(corpo["error"])[:200])

    resultado = corpo.get("result") or {}
    if resultado.get("isError"):
        raise OpggIndisponivel(f"ferramenta {nome} recusou: {str(resultado)[:200]}")

    partes = resultado.get("content") or []
    if not partes:
        raise OpggIndisponivel(f"ferramenta {nome} devolveu conteudo vazio")

    texto = partes[0].get("text") or ""
    try:
        return json.loads(texto)
    except ValueError:
        # Varias ferramentas respondem numa notacao compacta propria (nao
        # JSON). Quem precisar delas que parseie; devolver cru e melhor do que
        # falhar, e nenhum bloco exibe esse texto sem tratar.
        return texto


def analisar_notacao_compacta(texto: str, classe: str) -> list[dict[str, Any]]:
    """Le a notacao propria do OP.GG e devolve dicionarios.

    Varias ferramentas nao respondem JSON. Respondem um formato proprio que
    declara o schema no cabecalho e usa construtores posicionais no corpo:

        class Mid: champion,win_rate,pick_rate
        ...
        LolListLaneMetaChampions(Data(Positions([Mid("Ahri",0.51,0.09), ...])))

    O cabecalho e o que torna isso parseavel sem chutar: a ORDEM dos campos vem
    declarada, entao um campo novo do lado deles nao desloca os nossos em
    silencio - ele simplesmente aparece com o nome certo.

    Devolve `[]` quando a classe pedida nao esta no cabecalho, que e o que
    acontece se a ferramenta mudar de forma. Quem chama fica sem os dados, nao
    com dados errados.
    """
    cabecalho = re.search(rf"^class {re.escape(classe)}: (.+)$", texto, re.M)
    if not cabecalho:
        logger.warning("classe ausente na notacao do opgg", extra={"classe": classe})
        return []

    campos = [c.strip() for c in cabecalho.group(1).split(",")]
    linhas: list[dict[str, Any]] = []

    # `(?<![A-Za-z_])` evita casar `Mid(` dentro de `SomethingMid(`.
    for inicio in re.finditer(rf"(?<![A-Za-z_]){re.escape(classe)}\(", texto):
        argumentos = _argumentos_posicionais(texto, inicio.end())
        if argumentos is None or len(argumentos) != len(campos):
            continue
        linhas.append(dict(zip(campos, argumentos)))

    return linhas


def analisar_objeto_compacto(texto: str) -> Any:
    """Le a notacao compacta INTEIRA do OP.GG e devolve a arvore de dicts/listas.

    `analisar_notacao_compacta` extrai uma classe folha repetida (as tabelas de
    rota). Ja `lol_get_champion_analysis` responde uma ARVORE - build, runas,
    ordem de skill, combos, tudo aninhado - e essa precisa ser lida por inteiro:

        class Data: summary,core_items,boots,...
        class CoreItems: ids_names,play,win,pick_rate
        ...
        LolGetChampionAnalysis("Ahri",Data(CoreItems(["Malevolencia",...],...),...))

    Cada `Classe(a,b,c)` vira `{campo: valor}` pelos campos declarados no
    cabecalho; lista vira lista; escalar passa por `_valor`. Uma classe fora do
    cabecalho, ou com contagem de argumentos diferente da declarada, vira lista
    crua - quem le fica sem aquele ramo, nao com ramo errado.

    Devolve `None` se a expressao nao fecha (ferramenta mudou de forma).
    """
    esquema: dict[str, list[str]] = {}
    for m in re.finditer(r"^class (\w+): (.+)$", texto, re.M):
        esquema[m.group(1)] = [c.strip() for c in m.group(2).split(",")]

    corpo = [
        linha for linha in texto.splitlines()
        if linha and not linha.startswith("class ")
    ]
    if not corpo:
        return None
    s = "\n".join(corpo)
    pos = 0

    def _ws() -> None:
        nonlocal pos
        while pos < len(s) and s[pos] in " \t\n":
            pos += 1

    def _valor_texto() -> Any:
        nonlocal pos
        _ws()
        c = s[pos]
        if c == '"':
            return _str()
        if c == "[":
            return _lista()
        m = re.match(r"[A-Za-z_]\w*", s[pos:])
        if m and pos + m.end() < len(s) and s[pos + m.end()] == "(":
            return _objeto()
        return _escalar()

    def _str() -> str:
        nonlocal pos
        pos += 1
        buf: list[str] = []
        while pos < len(s):
            c = s[pos]
            pos += 1
            if c == "\\" and pos < len(s):
                buf.append(s[pos])
                pos += 1
                continue
            if c == '"':
                break
            buf.append(c)
        return "".join(buf)

    def _lista() -> list[Any]:
        nonlocal pos
        pos += 1
        out: list[Any] = []
        _ws()
        if pos < len(s) and s[pos] == "]":
            pos += 1
            return out
        while pos < len(s):
            out.append(_valor_texto())
            _ws()
            if s[pos] == ",":
                pos += 1
                continue
            if s[pos] == "]":
                pos += 1
                return out
        raise ValueError("lista sem `]`")

    def _objeto() -> Any:
        nonlocal pos
        m = re.match(r"[A-Za-z_]\w*", s[pos:])
        nome = m.group(0)
        pos += m.end() + 1
        args: list[Any] = []
        _ws()
        if pos < len(s) and s[pos] == ")":
            pos += 1
        else:
            while True:
                args.append(_valor_texto())
                _ws()
                if pos >= len(s):
                    raise ValueError("objeto sem `)`")
                if s[pos] == ",":
                    pos += 1
                    continue
                if s[pos] == ")":
                    pos += 1
                    break
        campos = esquema.get(nome)
        if campos and len(campos) == len(args):
            return dict(zip(campos, args))
        return args

    def _escalar() -> Any:
        nonlocal pos
        inicio = pos
        while pos < len(s) and s[pos] not in ",()[]":
            pos += 1
        return _valor(s[inicio:pos])

    try:
        return _valor_texto()
    except (IndexError, ValueError):
        return None


def _argumentos_posicionais(texto: str, posicao: int) -> list[Any] | None:
    """Os argumentos de uma chamada, a partir do caractere apos o parentese.

    Escrito a mao porque `split(",")` quebra em nome com virgula - e ha varios
    ("Nunu & Willump", "Renata Glasc"). O varredor respeita aspas e o
    escapamento delas.
    """
    argumentos: list[Any] = []
    atual: list[str] = []
    dentro_de_aspas = False
    escapado = False

    while posicao < len(texto):
        c = texto[posicao]
        posicao += 1

        if escapado:
            atual.append(c)
            escapado = False
            continue
        if c == "\\" and dentro_de_aspas:
            escapado = True
            continue
        if c == '"':
            dentro_de_aspas = not dentro_de_aspas
            atual.append(c)
            continue
        if dentro_de_aspas:
            atual.append(c)
            continue
        if c == ",":
            argumentos.append(_valor("".join(atual)))
            atual = []
            continue
        if c == ")":
            argumentos.append(_valor("".join(atual)))
            return argumentos
        # Um construtor aninhado no meio dos argumentos significa que esta nao
        # e a classe folha que o chamador quer - desiste em vez de adivinhar.
        if c == "(":
            return None
        atual.append(c)

    return None


def _valor(bruto: str) -> Any:
    """Converte um argumento cru no tipo dele."""
    bruto = bruto.strip()
    if bruto.startswith('"') and bruto.endswith('"'):
        return bruto[1:-1]
    if bruto in ("true", "false"):
        return bruto == "true"
    if bruto in ("null", "None", ""):
        return None
    try:
        return int(bruto)
    except ValueError:
        pass
    try:
        return float(bruto)
    except ValueError:
        return bruto


# ---------------------------------------------------------------------------
# VALORANT
# ---------------------------------------------------------------------------


def mapas_valorant() -> list[dict[str, str]]:
    """Os mapas do Valorant que o OP.GG tem estatistica: `[{id, nome}]`."""
    dados = chamar_ferramenta("valorant_list_maps", {})
    if isinstance(dados, dict):
        dados = dados.get("data")
    if not isinstance(dados, list):
        raise OpggIndisponivel("lista de mapas veio em formato inesperado")

    mapas: list[dict[str, str]] = []
    for bruto in dados:
        if not isinstance(bruto, dict):
            continue
        map_id = bruto.get("map_id")
        nome = (bruto.get("names") or {}).get("pt_BR") or bruto.get("name")
        if isinstance(map_id, str) and isinstance(nome, str):
            mapas.append({"id": map_id, "nome": nome})
    return mapas


def _metricas_taticas(bruto: dict[str, Any]) -> dict[str, float | None]:
    """As metricas do genero tatico, derivadas dos brutos do OP.GG.

    Nao ha estimativa aqui, so divisao. Extraida para servir os dois recortes -
    o agregado geral do agente e o de cada mapa -, que compartilham exatamente
    a mesma conta.
    """
    tiros = (
        (bruto.get("headShots") or 0)
        + (bruto.get("bodyShots") or 0)
        + (bruto.get("legShots") or 0)
    )
    rounds = bruto.get("rounds") or 0
    mortes = bruto.get("deaths") or 0
    primeiros = (bruto.get("firstKills") or 0) + (bruto.get("firstDeaths") or 0)

    return {
        # Sobre TIROS DADOS, nao sobre abates: e assim que a comunidade do
        # genero le "HS%", e o denominador certo e o que a mira controla.
        "hs": round(100 * (bruto.get("headShots") or 0) / tiros, 1) if tiros else None,
        "adr": round((bruto.get("damage") or 0) / rounds, 1) if rounds else None,
        "acs": round((bruto.get("score") or 0) / rounds, 1) if rounds else None,
        # Sem morte nenhuma o KDA seria divisao por zero; a convencao do genero
        # e dividir por 1.
        "kda": round(
            ((bruto.get("kills") or 0) + (bruto.get("assists") or 0)) / max(1, mortes), 2
        ),
        # Duelo de abertura ganho sobre duelo de abertura disputado.
        "entrada": round(100 * (bruto.get("firstKills") or 0) / primeiros, 1)
        if primeiros
        else None,
        "spike": round(
            ((bruto.get("bombPlantings") or 0) + (bruto.get("bombDefusings") or 0))
            / rounds,
            3,
        )
        if rounds
        else None,
    }


def estatisticas_agentes_valorant(
    map_id: str | None = None,
) -> list[dict[str, Any]]:
    """Desempenho agregado por agente: partidas, vitorias, derrotas, abates.

    Sem `map_id`, e o agregado GERAL do agente. Com `map_id`, e o recorte
    daquele mapa - o mesmo `valorant_list_agent_statistics`, so que filtrado.
    O recorte por mapa e o que da profundidade ao detalhe do agente: a media
    geral esconde que um agente e forte num mapa e fraco noutro.

    A chave e `characterId`, o MESMO uuid que a valorant-api.com usa - entao a
    estatistica casa com `dim_personagem` sem heuristica de nome.

    Estes numeros sao do publico geral do OP.GG (centenas de milhares de
    partidas por agente), NAO do cenario profissional.
    """
    argumentos = {"map_id": map_id} if map_id else {}
    dados = chamar_ferramenta("valorant_list_agent_statistics", argumentos)
    if isinstance(dados, dict):
        dados = dados.get("data")
    if not isinstance(dados, list):
        raise OpggIndisponivel("estatistica de agente veio em formato inesperado")

    agentes: list[dict[str, Any]] = []
    for bruto in dados:
        if not isinstance(bruto, dict):
            continue
        uuid = bruto.get("characterId")
        partidas = bruto.get("gameCount") or 0
        vitorias = bruto.get("wins") or 0
        derrotas = bruto.get("defeats") or 0
        decididas = vitorias + derrotas
        if not isinstance(uuid, str) or not decididas:
            continue

        agentes.append(
            {
                # Minusculo: e assim que a valorant-api.com entrega, e e assim
                # que esta gravado em `dim_personagem.id_externo`.
                "id_externo": uuid.lower(),
                "partidas": partidas,
                "vitorias": vitorias,
                "derrotas": derrotas,
                # Empate existe no Valorant e nao cabe em "venceu ou perdeu":
                # fica fora do denominador em vez de contar como meia derrota.
                "winrate": round(100 * vitorias / decididas, 1),
                "metricas": _metricas_taticas(bruto),
            }
        )

    total = sum(a["partidas"] for a in agentes)
    for agente in agentes:
        # Taxa de escolha sobre o total de PARTIDAS-agente da amostra. Nao e o
        # mesmo que "porcentagem de partidas em que apareceu" (cada partida tem
        # dez agentes).
        agente["pick_rate"] = round(100 * agente["partidas"] / total, 1) if total else 0.0

    return agentes
