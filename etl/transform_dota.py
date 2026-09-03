"""Normalizacao dos payloads do OpenDota para o star schema de partidas.

Funcoes puras sobre dicionarios: sem rede, sem banco. Este arquivo e o lugar
onde o vocabulario do Dota ("hero", "radiant", "roshan") vira o vocabulario
generico do modelo dimensional, que precisa servir tambem para LoL e Valorant.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, Field

from collectors.base import RawRecord

logger = logging.getLogger(__name__)

FONTE = "opendota"
JOGO = "dota2"

ENDPOINT_HEROIS = "heroes"
ENDPOINT_LISTA = "promatches"
ENDPOINT_PARTIDA = "match"

TIPO_PROFISSIONAL = "profissional"

# game_mode do OpenDota -> rotulo legivel. O que nao estiver aqui vira
# "modo_<n>" em vez de virar NULL: perder a informacao seria pior.
MODOS = {
    1: "all pick",
    2: "captains mode",
    3: "random draft",
    4: "single draft",
    5: "all random",
    16: "captains draft",
    22: "all draft (ranqueada)",
    23: "turbo",
}

# lane_role -> funcao generica. No LoL vira top/mid/bot/jungle/support.
FUNCOES = {1: "safe", 2: "mid", 3: "off", 4: "jungle"}


# ---------------------------------------------------------------------------
# Modelos normalizados
# ---------------------------------------------------------------------------


class Personagem(BaseModel):
    """Linha de dim_personagem. Heroi, campeao e agente sao o mesmo conceito."""

    id_externo: str
    nome: str
    nome_interno: str | None = None


class Jogador(BaseModel):
    """Linha de dim_jogador."""

    id_externo: str
    nome: str | None = None
    regiao: str | None = None


class Equipe(BaseModel):
    """Linha de dim_equipe."""

    id_externo: str
    nome: str
    tag: str | None = None
    logo_url: str | None = None


class Partida(BaseModel):
    """Linha de dim_partida."""

    id_externo: str
    data_inicio: datetime | None = None
    id_tempo: int | None = None
    duracao_segundos: int | None = None
    modo: str | None = None
    tipo_partida: str = TIPO_PROFISSIONAL
    patch: str | None = None
    liga_nome: str | None = None
    liga_id_externo: str | None = None
    liga_tier: str | None = None
    #: `team_id` de cada lado. Nulo quando a fonte nao cadastrou o time.
    equipe_lado_a_externo: str | None = None
    equipe_lado_b_externo: str | None = None


class Participacao(BaseModel):
    """Linha de fato_partida_jogador - o grao do dominio de partidas."""

    id_partida_externo: str
    id_jogador_externo: str | None = None
    id_personagem_externo: str | None = None
    id_tempo: int | None = None
    equipe: str | None = None
    slot: int
    vitoria: bool | None = None
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    dano_causado: int | None = None
    dano_recebido: int | None = None
    economia: int | None = None
    economia_por_minuto: int | None = None
    experiencia_por_minuto: int | None = None
    pontos_objetivo: int | None = None
    last_hits: int | None = None
    denies: int | None = None
    nivel: int | None = None
    funcao: str | None = None
    duracao_partida_segundos: int | None = None
    metricas_extras: dict[str, Any] = Field(default_factory=dict)


class MinutoPartida(BaseModel):
    """Linha de fato_minuto_partida - o estado do mapa no minuto N.

    Tudo e do ponto de vista do lado A (radiant no Dota): vantagem positiva
    significa lado A na frente.
    """

    id_partida_externo: str
    minuto: int
    vantagem_economia: int | None = None
    vantagem_experiencia: int | None = None
    torres_perdidas_lado_a: int = 0
    torres_perdidas_lado_b: int = 0
    objetivos_maiores_lado_a: int = 0
    objetivos_maiores_lado_b: int = 0
    vitoria_lado_a: bool | None = None


class ResultadoDota(BaseModel):
    personagens: list[Personagem] = Field(default_factory=list)
    jogadores: list[Jogador] = Field(default_factory=list)
    partidas: list[Partida] = Field(default_factory=list)
    participacoes: list[Participacao] = Field(default_factory=list)
    minutos: list[MinutoPartida] = Field(default_factory=list)
    equipes: list[Equipe] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.personagens)
            + len(self.jogadores)
            + len(self.partidas)
            + len(self.participacoes)
            + len(self.minutos)
            + len(self.equipes)
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _inteiro(valor: Any) -> int | None:
    """Converte para int tolerando None, string e bool."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def epoch_para_datetime(valor: Any) -> datetime | None:
    segundos = _inteiro(valor)
    if not segundos or segundos <= 0:
        return None
    return datetime.fromtimestamp(segundos, tz=timezone.utc)


def chave_tempo(momento: datetime | None) -> int | None:
    """Data no formato AAAAMMDD, a chave primaria de dim_tempo."""
    if momento is None:
        return None
    return int(momento.astimezone(timezone.utc).strftime("%Y%m%d"))


def _soma_opcional(*valores: Any) -> int | None:
    """Soma ignorando None. Devolve None se nada for somavel."""
    numeros = [n for n in (_inteiro(v) for v in valores) if n is not None]
    return sum(numeros) if numeros else None


def nome_do_modo(game_mode: Any) -> str | None:
    codigo = _inteiro(game_mode)
    if codigo is None:
        return None
    return MODOS.get(codigo, f"modo_{codigo}")


# ---------------------------------------------------------------------------
# Parsers por endpoint
# ---------------------------------------------------------------------------


def parse_herois(payload: Any) -> list[Personagem]:
    """/heroes -> dimensao de personagens do Dota."""
    if not isinstance(payload, list):
        return []

    personagens: list[Personagem] = []
    for heroi in payload:
        if not isinstance(heroi, dict):
            continue
        id_externo = _inteiro(heroi.get("id"))
        nome = heroi.get("localized_name") or heroi.get("name")
        if id_externo is None or not nome:
            continue
        personagens.append(
            Personagem(
                id_externo=str(id_externo),
                nome=str(nome),
                nome_interno=heroi.get("name"),
            )
        )
    return personagens


def parse_partida(payload: Any) -> Partida | None:
    """/matches/{id} -> linha da dimensao de partida."""
    if not isinstance(payload, dict):
        return None
    match_id = _inteiro(payload.get("match_id"))
    if match_id is None:
        return None

    inicio = epoch_para_datetime(payload.get("start_time"))
    patch = payload.get("patch")
    liga = payload.get("league") if isinstance(payload.get("league"), dict) else {}

    equipes = {
        lado: payload.get(chave) if isinstance(payload.get(chave), dict) else {}
        for lado, chave in (("a", "radiant_team"), ("b", "dire_team"))
    }

    return Partida(
        id_externo=str(match_id),
        data_inicio=inicio,
        id_tempo=chave_tempo(inicio),
        duracao_segundos=_inteiro(payload.get("duration")),
        modo=nome_do_modo(payload.get("game_mode")),
        tipo_partida=TIPO_PROFISSIONAL,
        # O OpenDota devolve o patch como indice numerico; guardamos como texto
        # porque LoL e Valorant usam versao no formato "14.5".
        patch=str(patch) if patch is not None else None,
        liga_nome=payload.get("league_name") or liga.get("name"),
        liga_id_externo=(
            str(payload["leagueid"]) if _inteiro(payload.get("leagueid")) else None
        ),
        liga_tier=liga.get("tier"),
        equipe_lado_a_externo=(
            str(equipes["a"]["team_id"]) if _inteiro(equipes["a"].get("team_id")) else None
        ),
        equipe_lado_b_externo=(
            str(equipes["b"]["team_id"]) if _inteiro(equipes["b"].get("team_id")) else None
        ),
    )


def parse_equipes(payload: Any) -> list[Equipe]:
    """/matches/{id} -> as duas equipes da partida, quando a fonte as cadastrou.

    `radiant_team` e `dire_team` sao objetos separados de `radiant_name`: o nome
    solto aparece em partida sem time cadastrado, e ali nao ha `team_id` - sem
    chave natural, a linha nao pode entrar na dimensao sem duplicar a cada
    coleta. Por isso so entra quem tem `team_id`.
    """
    if not isinstance(payload, dict):
        return []

    equipes: list[Equipe] = []
    for chave in ("radiant_team", "dire_team"):
        bruta = payload.get(chave)
        if not isinstance(bruta, dict):
            continue

        id_externo = _inteiro(bruta.get("team_id"))
        nome = bruta.get("name")
        if not id_externo or not nome:
            continue

        equipes.append(
            Equipe(
                id_externo=str(id_externo),
                nome=str(nome)[:120],
                tag=bruta.get("tag"),
                logo_url=bruta.get("logo_url"),
            )
        )
    return equipes


def _extrair_jogador(bruto: dict[str, Any]) -> Jogador | None:
    """None quando a API anonimiza o jogador (account_id ausente ou 0)."""
    account_id = _inteiro(bruto.get("account_id"))
    if not account_id:
        return None
    return Jogador(
        id_externo=str(account_id),
        nome=bruto.get("personaname") or bruto.get("name"),
        regiao=str(bruto["region"]) if _inteiro(bruto.get("region")) else None,
    )


def _dano_recebido(bruto: dict[str, Any]) -> int | None:
    """damage_taken vem como dicionario por fonte de dano; somamos tudo."""
    valor = bruto.get("damage_taken")
    if isinstance(valor, dict):
        return _soma_opcional(*valor.values())
    return _inteiro(valor)


def _metricas_extras(bruto: dict[str, Any]) -> dict[str, Any]:
    """Metricas exclusivas do Dota, fora das colunas compartilhadas.

    Ficam em JSONB para nao criar colunas que LoL e Valorant nunca preencheriam.
    """
    campos = (
        "hero_healing",
        "lane_efficiency_pct",
        "actions_per_min",
        "obs_placed",
        "sen_placed",
        "camps_stacked",
        "towers_killed",
        "roshan_kills",
        "rank_tier",
        "tower_damage",
        "net_worth",
    )
    return {campo: bruto[campo] for campo in campos if bruto.get(campo) is not None}


def parse_participacoes(payload: Any) -> tuple[list[Participacao], list[Jogador]]:
    """/matches/{id} -> uma linha de fato por jogador, mais os jogadores vistos."""
    if not isinstance(payload, dict):
        return [], []

    match_id = _inteiro(payload.get("match_id"))
    jogadores_brutos = payload.get("players")
    if match_id is None or not isinstance(jogadores_brutos, list):
        return [], []

    inicio = epoch_para_datetime(payload.get("start_time"))
    id_tempo = chave_tempo(inicio)
    duracao = _inteiro(payload.get("duration"))
    radiant_venceu = payload.get("radiant_win")

    participacoes: list[Participacao] = []
    jogadores: list[Jogador] = []

    for bruto in jogadores_brutos:
        if not isinstance(bruto, dict):
            continue

        slot = _inteiro(bruto.get("player_slot"))
        if slot is None:
            continue

        # player_slot 0-4 e Radiant, 128-132 e Dire. isRadiant e derivado disso
        # pelo OpenDota, mas nem sempre vem preenchido.
        e_radiant = bruto.get("isRadiant")
        if e_radiant is None:
            e_radiant = slot < 128

        vitoria = bruto.get("win")
        if vitoria is None and isinstance(radiant_venceu, bool):
            vitoria = radiant_venceu == bool(e_radiant)

        jogador = _extrair_jogador(bruto)
        if jogador is not None:
            jogadores.append(jogador)

        heroi = _inteiro(bruto.get("hero_id"))

        participacoes.append(
            Participacao(
                id_partida_externo=str(match_id),
                id_jogador_externo=jogador.id_externo if jogador else None,
                id_personagem_externo=str(heroi) if heroi else None,
                id_tempo=id_tempo,
                equipe="radiant" if e_radiant else "dire",
                slot=slot,
                vitoria=bool(vitoria) if vitoria is not None else None,
                kills=_inteiro(bruto.get("kills")),
                deaths=_inteiro(bruto.get("deaths")),
                assists=_inteiro(bruto.get("assists")),
                dano_causado=_inteiro(bruto.get("hero_damage")),
                dano_recebido=_dano_recebido(bruto),
                economia=_inteiro(bruto.get("total_gold")),
                economia_por_minuto=_inteiro(bruto.get("gold_per_min")),
                experiencia_por_minuto=_inteiro(bruto.get("xp_per_min")),
                # Objetivo generico: torres + Roshan. No LoL sera torres +
                # dragoes + barao; no Valorant, spikes plantadas/desarmadas.
                pontos_objetivo=_soma_opcional(
                    bruto.get("towers_killed"), bruto.get("roshan_kills")
                ),
                last_hits=_inteiro(bruto.get("last_hits")),
                denies=_inteiro(bruto.get("denies")),
                nivel=_inteiro(bruto.get("level")),
                funcao=FUNCOES.get(_inteiro(bruto.get("lane_role")) or -1),
                duracao_partida_segundos=duracao,
                metricas_extras=_metricas_extras(bruto),
            )
        )

    return participacoes, jogadores


# Ids de equipe do Dota nos eventos de objetivo.
EQUIPE_RADIANT = 2
EQUIPE_DIRE = 3

# Os objetivos que mudam o mapa de verdade. Courier perdido e primeiro sangue
# aparecem na mesma lista e nao entram: sao eventos de placar, nao de estado.
OBJETIVOS_MAIORES = {"CHAT_MESSAGE_ROSHAN_KILL", "CHAT_MESSAGE_MINIBOSS_KILL"}


def _minuto(segundos: Any) -> int | None:
    """Segundos do relogio da partida -> minuto inteiro. Descarta o pre-jogo."""
    valor = _inteiro(segundos)
    if valor is None or valor < 0:
        return None
    return valor // 60


def parse_serie_minutos(payload: Any) -> list[MinutoPartida]:
    """/matches/{id} -> uma linha por minuto de partida.

    A OpenDota publica `radiant_gold_adv` e `radiant_xp_adv` como listas ja
    indexadas por minuto - o indice E o minuto. Torres e Roshans vem como
    eventos com carimbo de tempo, entao aqui eles viram contagem ACUMULADA ate
    cada minuto: o modelo preve a partir do estado do mapa, e estado e
    cumulativo. Somar so o que aconteceu naquele minuto responderia outra
    pergunta.
    """
    if not isinstance(payload, dict):
        return []

    match_id = _inteiro(payload.get("match_id"))
    economia = payload.get("radiant_gold_adv")
    if match_id is None or not isinstance(economia, list) or not economia:
        # Partida sem curva de vantagem (replay nao parseado pela OpenDota) nao
        # gera serie. E o caso de boa parte das partidas publicas.
        return []

    experiencia = payload.get("radiant_xp_adv")
    if not isinstance(experiencia, list):
        experiencia = []

    vitoria = payload.get("radiant_win")
    vitoria_lado_a = bool(vitoria) if isinstance(vitoria, bool) else None

    # Eventos -> dois acumuladores por minuto, um por lado.
    torres: dict[int, list[int]] = {}
    objetivos: dict[int, list[int]] = {}

    for evento in payload.get("objectives") or []:
        if not isinstance(evento, dict):
            continue
        minuto = _minuto(evento.get("time"))
        if minuto is None:
            continue

        tipo = evento.get("type")

        if tipo == "building_kill":
            # A chave nomeia a construcao DESTRUIDA, entao "badguys" (dire) na
            # chave significa que quem perdeu a torre foi o lado B.
            chave = str(evento.get("key") or "")
            if "tower" not in chave:
                continue  # racks e fort nao entram: nao sao torre
            if "goodguys" in chave:
                torres.setdefault(minuto, [0, 0])[0] += 1
            elif "badguys" in chave:
                torres.setdefault(minuto, [0, 0])[1] += 1

        elif tipo in OBJETIVOS_MAIORES:
            equipe = _inteiro(evento.get("team"))
            if equipe == EQUIPE_RADIANT:
                objetivos.setdefault(minuto, [0, 0])[0] += 1
            elif equipe == EQUIPE_DIRE:
                objetivos.setdefault(minuto, [0, 0])[1] += 1

    linhas: list[MinutoPartida] = []
    torres_a = torres_b = obj_a = obj_b = 0

    for minuto in range(len(economia)):
        incremento_torre = torres.get(minuto)
        if incremento_torre:
            torres_a += incremento_torre[0]
            torres_b += incremento_torre[1]

        incremento_objetivo = objetivos.get(minuto)
        if incremento_objetivo:
            obj_a += incremento_objetivo[0]
            obj_b += incremento_objetivo[1]

        linhas.append(
            MinutoPartida(
                id_partida_externo=str(match_id),
                minuto=minuto,
                vantagem_economia=_inteiro(economia[minuto]),
                vantagem_experiencia=(
                    _inteiro(experiencia[minuto]) if minuto < len(experiencia) else None
                ),
                torres_perdidas_lado_a=torres_a,
                torres_perdidas_lado_b=torres_b,
                objetivos_maiores_lado_a=obj_a,
                objetivos_maiores_lado_b=obj_b,
                vitoria_lado_a=vitoria_lado_a,
            )
        )

    return linhas


# ---------------------------------------------------------------------------
# Montagem do resultado
# ---------------------------------------------------------------------------


def transformar(registros: Iterable[RawRecord]) -> ResultadoDota:
    """Consolida os registros brutos de uma coleta em um ResultadoDota."""
    personagens: dict[str, Personagem] = {}
    jogadores: dict[str, Jogador] = {}
    partidas: dict[str, Partida] = {}
    participacoes: dict[tuple[str, int], Participacao] = {}
    minutos: dict[tuple[str, int], MinutoPartida] = {}
    equipes: dict[str, Equipe] = {}

    for registro in registros:
        if registro.fonte != FONTE:
            continue

        if registro.endpoint == ENDPOINT_HEROIS:
            for personagem in parse_herois(registro.payload):
                personagens[personagem.id_externo] = personagem
            continue

        if registro.endpoint != ENDPOINT_PARTIDA:
            # /proMatches so serve para descobrir match_ids; o dado analitico
            # vem do detalhe de cada partida.
            continue

        partida = parse_partida(registro.payload)
        if partida is None:
            logger.warning(
                "payload de partida sem match_id, ignorado",
                extra={"identificador": registro.identificador},
            )
            continue

        novas_participacoes, novos_jogadores = parse_participacoes(registro.payload)
        if not novas_participacoes:
            # Partida sem jogadores nao gera fato; guardar so a dimensao
            # inflaria dim_partida com linhas que ninguem consulta.
            logger.warning(
                "partida sem jogadores, ignorada",
                extra={"partida": partida.id_externo},
            )
            continue

        partidas[partida.id_externo] = partida
        for jogador in novos_jogadores:
            jogadores[jogador.id_externo] = jogador
        for participacao in novas_participacoes:
            chave = (participacao.id_partida_externo, participacao.slot)
            participacoes[chave] = participacao
        for minuto in parse_serie_minutos(registro.payload):
            minutos[(minuto.id_partida_externo, minuto.minuto)] = minuto
        for equipe in parse_equipes(registro.payload):
            equipes[equipe.id_externo] = equipe

    return ResultadoDota(
        personagens=list(personagens.values()),
        jogadores=list(jogadores.values()),
        partidas=list(partidas.values()),
        participacoes=list(participacoes.values()),
        minutos=list(minutos.values()),
        equipes=list(equipes.values()),
    )
