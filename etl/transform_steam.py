"""Normalizacao dos payloads da Steam.

Tudo aqui e funcao pura sobre dicionarios: nada de rede, nada de banco. E o
ponto mais fragil do sistema (a Steam muda campos sem aviso), por isso e
tambem a parte com testes de fixture em `tests/`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Sequence

from pydantic import BaseModel, Field

from collectors.base import RawRecord

logger = logging.getLogger(__name__)

FONTE = "steam"
ENDPOINT_DETALHES = "appdetails"
ENDPOINT_AVALIACOES = "appreviews"
ENDPOINT_JOGADORES = "numberofcurrentplayers"

# A Steam localiza a data conforme o parametro `l`. Coletamos com l=english
# justamente para cair em um destes formatos.
_FORMATOS_DATA = ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y", "%b %Y", "%B %Y", "%Y")


# ---------------------------------------------------------------------------
# Modelos normalizados
# ---------------------------------------------------------------------------


class JogoSteam(BaseModel):
    """Linha da dimensao `dim_jogo_steam`."""

    app_id: int
    nome: str
    tipo: str | None = None
    desenvolvedora: str | None = None
    publicadora: str | None = None
    data_lancamento: date | None = None
    data_lancamento_texto: str | None = None
    generos: list[str] = Field(default_factory=list)
    gratuito: bool | None = None
    preco_atual: Decimal | None = None
    moeda: str | None = None
    nota_metacritic: int | None = None


class SnapshotSteam(BaseModel):
    """Linha do fato `fato_snapshot_jogo_steam`."""

    app_id: int
    janela_coleta: datetime
    data_coleta: datetime
    jogadores_simultaneos: int | None = None
    nota_avaliacoes: Decimal | None = None
    numero_avaliacoes: int | None = None
    avaliacoes_positivas: int | None = None
    avaliacoes_negativas: int | None = None
    classificacao_steam: str | None = None
    preco_no_momento: Decimal | None = None
    moeda: str | None = None
    desconto_percentual: int | None = None


class AvaliacaoSteam(BaseModel):
    """Linha de fato_avaliacao_steam - uma avaliacao escrita, com o texto."""

    app_id: int
    id_externo: str
    idioma: str | None = None
    texto: str
    #: O polegar do proprio autor. E o rotulo do modelo de sentimento.
    recomendado: bool
    criada_em: datetime | None = None
    minutos_jogados: int | None = None
    votos_uteis: int | None = None
    votos_engracados: int | None = None
    compra_na_steam: bool | None = None
    recebido_de_graca: bool | None = None
    acesso_antecipado: bool | None = None


class ResultadoSteam(BaseModel):
    jogos: list[JogoSteam] = Field(default_factory=list)
    snapshots: list[SnapshotSteam] = Field(default_factory=list)
    avaliacoes: list[AvaliacaoSteam] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.jogos) + len(self.snapshots) + len(self.avaliacoes)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def truncar_janela(momento: datetime, minutos: int) -> datetime:
    """Alinha um instante ao inicio da janela de coleta (chave de idempotencia)."""
    if minutos <= 0:
        raise ValueError("minutos deve ser positivo")
    momento = momento.astimezone(timezone.utc)
    inicio_do_dia = momento.replace(hour=0, minute=0, second=0, microsecond=0)
    decorridos = int((momento - inicio_do_dia).total_seconds() // 60)
    return inicio_do_dia + timedelta(minutes=(decorridos // minutos) * minutos)


def _inteiro(valor: Any) -> int | None:
    """Converte para int tolerando None, string e bool."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _epoch_para_datetime(valor: Any) -> datetime | None:
    """Epoch em segundos -> datetime UTC. A Steam carimba as avaliacoes assim."""
    segundos = _inteiro(valor)
    if segundos is None or segundos <= 0:
        return None
    return datetime.fromtimestamp(segundos, tz=timezone.utc)


def parse_data_lancamento(texto: str | None) -> date | None:
    """Converte a data textual da Steam. Devolve None quando nao e uma data.

    Valores como "Coming soon", "Q3 2025" ou "To be announced" sao comuns e
    nao devem quebrar o ETL - viram None, com o texto original preservado.
    """
    if not texto:
        return None
    limpo = texto.strip()
    for formato in _FORMATOS_DATA:
        try:
            return datetime.strptime(limpo, formato).date()
        except ValueError:
            continue
    logger.debug("data de lancamento nao parseavel", extra={"texto": limpo})
    return None


def _centavos_para_decimal(valor: Any) -> Decimal | None:
    if valor is None:
        return None
    try:
        return (Decimal(int(valor)) / Decimal(100)).quantize(Decimal("0.01"))
    except (TypeError, ValueError, ArithmeticError):
        return None


def _juntar(valores: Any) -> str | None:
    if not valores:
        return None
    if isinstance(valores, str):
        return valores
    itens = [str(v).strip() for v in valores if str(v).strip()]
    return ", ".join(itens) or None


def _extrair_dados_appdetails(payload: Any, app_id: int) -> dict[str, Any] | None:
    """A resposta vem como {"<app_id>": {"success": bool, "data": {...}}}.

    Guardamos o payload inteiro no raw, entao aceitamos tanto o envelope
    completo quanto o objeto interno ja desembrulhado.
    """
    if not isinstance(payload, dict):
        return None
    entrada = payload.get(str(app_id), payload)
    if not isinstance(entrada, dict):
        return None
    if entrada.get("success") is False:
        return None
    dados = entrada.get("data", entrada)
    return dados if isinstance(dados, dict) and dados.get("steam_appid") else None


# ---------------------------------------------------------------------------
# Parsers por endpoint
# ---------------------------------------------------------------------------


def parse_appdetails(payload: Any, app_id: int) -> JogoSteam | None:
    """appdetails -> dimensao do jogo. None quando a Steam nega o app."""
    dados = _extrair_dados_appdetails(payload, app_id)
    if dados is None:
        logger.warning("appdetails sem dados utilizaveis", extra={"app_id": app_id})
        return None

    preco = dados.get("price_overview") or {}
    metacritic = dados.get("metacritic") or {}
    lancamento = dados.get("release_date") or {}
    data_texto = lancamento.get("date") or None

    return JogoSteam(
        app_id=int(dados.get("steam_appid", app_id)),
        nome=str(dados.get("name") or f"app-{app_id}"),
        tipo=dados.get("type"),
        desenvolvedora=_juntar(dados.get("developers")),
        publicadora=_juntar(dados.get("publishers")),
        data_lancamento=parse_data_lancamento(data_texto),
        data_lancamento_texto=data_texto,
        generos=[
            str(g.get("description"))
            for g in dados.get("genres") or []
            if isinstance(g, dict) and g.get("description")
        ],
        gratuito=dados.get("is_free"),
        preco_atual=_centavos_para_decimal(preco.get("final")),
        moeda=preco.get("currency"),
        nota_metacritic=metacritic.get("score"),
    )


def parse_preco(payload: Any, app_id: int) -> dict[str, Any]:
    """Parte do appdetails que varia no tempo e por isso vai para o fato."""
    dados = _extrair_dados_appdetails(payload, app_id) or {}
    preco = dados.get("price_overview") or {}
    gratuito = dados.get("is_free")

    valor = _centavos_para_decimal(preco.get("final"))
    if valor is None and gratuito:
        valor = Decimal("0.00")

    return {
        "preco_no_momento": valor,
        "moeda": preco.get("currency"),
        "desconto_percentual": preco.get("discount_percent"),
    }


def parse_appreviews(payload: Any) -> dict[str, Any]:
    """appreviews?num_per_page=0 -> so o query_summary agregado."""
    if not isinstance(payload, dict) or payload.get("success") != 1:
        return {}

    resumo = payload.get("query_summary") or {}
    positivas = resumo.get("total_positive")
    negativas = resumo.get("total_negative")
    total = resumo.get("total_reviews")

    nota: Decimal | None = None
    if isinstance(positivas, int) and isinstance(total, int) and total > 0:
        nota = (Decimal(positivas) * 100 / Decimal(total)).quantize(Decimal("0.01"))

    return {
        "avaliacoes_positivas": positivas,
        "avaliacoes_negativas": negativas,
        "numero_avaliacoes": total,
        "nota_avaliacoes": nota,
        "classificacao_steam": resumo.get("review_score_desc"),
    }


def parse_avaliacoes(payload: Any, app_id: int) -> list[AvaliacaoSteam]:
    """appreviews com `num_per_page > 0` -> uma linha por avaliacao escrita.

    O mesmo payload que alimenta o resumo agregado traz a lista quando o coletor
    pede texto. Sao dois GRAOS diferentes saindo de uma chamada so - e o motivo
    de nao existir um segundo endpoint: pedir de novo gastaria o mesmo balde de
    rate limit para trazer o que ja veio.

    Avaliacao sem texto e descartada: ela existe na Steam (da para dar o polegar
    sem escrever nada), mas uma linha vazia nao ensina nada a um classificador
    de texto e ainda entraria na contagem como se ensinasse.
    """
    if not isinstance(payload, dict) or payload.get("success") != 1:
        return []

    brutas = payload.get("reviews")
    if not isinstance(brutas, list):
        return []

    avaliacoes: list[AvaliacaoSteam] = []
    for bruta in brutas:
        if not isinstance(bruta, dict):
            continue

        id_externo = bruta.get("recommendationid")
        texto = (bruta.get("review") or "").strip()
        recomendado = bruta.get("voted_up")

        if not id_externo or not texto or not isinstance(recomendado, bool):
            continue

        autor = bruta.get("author") if isinstance(bruta.get("author"), dict) else {}

        avaliacoes.append(
            AvaliacaoSteam(
                app_id=app_id,
                id_externo=str(id_externo),
                idioma=bruta.get("language"),
                texto=texto,
                recomendado=recomendado,
                criada_em=_epoch_para_datetime(bruta.get("timestamp_created")),
                minutos_jogados=_inteiro(autor.get("playtime_forever")),
                votos_uteis=_inteiro(bruta.get("votes_up")),
                votos_engracados=_inteiro(bruta.get("votes_funny")),
                compra_na_steam=bruta.get("steam_purchase"),
                recebido_de_graca=bruta.get("received_for_free"),
                acesso_antecipado=bruta.get("written_during_early_access"),
            )
        )

    return avaliacoes


def parse_jogadores_simultaneos(payload: Any) -> int | None:
    """GetNumberOfCurrentPlayers -> contagem, ou None se o app nao expoe."""
    if not isinstance(payload, dict):
        return None
    resposta = payload.get("response") or {}
    if resposta.get("result") != 1:
        return None
    contagem = resposta.get("player_count")
    return int(contagem) if isinstance(contagem, int) else None


# ---------------------------------------------------------------------------
# Montagem do resultado
# ---------------------------------------------------------------------------


def transformar(
    registros: Iterable[RawRecord], janela_minutos: int = 60
) -> ResultadoSteam:
    """Agrupa os RawRecord's por app_id e monta dimensao, snapshot e avaliacoes.

    Cada app_id gera no maximo uma linha de dimensao e uma de snapshot, ainda
    que venha de tres endpoints diferentes. As avaliacoes sao a excecao: o
    coletor pagina o endpoint de reviews, entao chegam VARIOS registros do
    mesmo endpoint para o mesmo app, e todos entram. Por isso o agrupamento
    guarda uma lista por endpoint em vez de um registro so - com um registro
    so, a ultima pagina apagaria as anteriores em silencio.
    """
    por_app: dict[int, dict[str, list[RawRecord]]] = {}
    for registro in registros:
        if registro.fonte != FONTE:
            continue
        try:
            app_id = int(registro.identificador)
        except ValueError:
            logger.warning(
                "identificador nao numerico ignorado",
                extra={"identificador": registro.identificador},
            )
            continue
        por_app.setdefault(app_id, {}).setdefault(registro.endpoint, []).append(
            registro
        )

    resultado = ResultadoSteam()
    for app_id, endpoints in sorted(por_app.items()):
        paginas_detalhes = endpoints.get(ENDPOINT_DETALHES, [])
        paginas_avaliacoes = endpoints.get(ENDPOINT_AVALIACOES, [])
        paginas_jogadores = endpoints.get(ENDPOINT_JOGADORES, [])

        detalhes = paginas_detalhes[0] if paginas_detalhes else None
        # O resumo agregado e igual em toda pagina; basta a primeira.
        avaliacoes = paginas_avaliacoes[0] if paginas_avaliacoes else None
        jogadores = paginas_jogadores[0] if paginas_jogadores else None

        jogo = parse_appdetails(detalhes.payload, app_id) if detalhes else None
        if jogo is not None:
            resultado.jogos.append(jogo)

        # Sem dimensao nao ha FK possivel; o snapshot seria orfao.
        if jogo is None:
            continue

        momento = max(
            registro.coletado_em
            for pagina in endpoints.values()
            for registro in pagina
        ).astimezone(timezone.utc)

        campos: dict[str, Any] = {
            "app_id": app_id,
            "data_coleta": momento,
            "janela_coleta": truncar_janela(momento, janela_minutos),
        }
        if detalhes:
            campos.update(parse_preco(detalhes.payload, app_id))
        if avaliacoes:
            campos.update(parse_appreviews(avaliacoes.payload))
        if jogadores:
            campos["jogadores_simultaneos"] = parse_jogadores_simultaneos(
                jogadores.payload
            )

        resultado.snapshots.append(SnapshotSteam(**campos))

        # As avaliacoes vem de TODAS as paginas, nao so da primeira.
        vistas: set[str] = set()
        for pagina in paginas_avaliacoes:
            for avaliacao in parse_avaliacoes(pagina.payload, app_id):
                # A Steam repete linhas na virada de cursor quando alguem
                # publica uma avaliacao entre duas chamadas; sem a deduplicacao
                # o INSERT quebraria com duas linhas da mesma chave no lote.
                if avaliacao.id_externo in vistas:
                    continue
                vistas.add(avaliacao.id_externo)
                resultado.avaliacoes.append(avaliacao)

    return resultado


def transformar_lista(
    registros: Sequence[RawRecord], janela_minutos: int = 60
) -> ResultadoSteam:
    """Alias explicito para uso na CLI/testes."""
    return transformar(registros, janela_minutos)
