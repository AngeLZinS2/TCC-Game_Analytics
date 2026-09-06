"""Previsao de confronto: qual time tem mais chance de vencer, e por que.

Nada da partida aconteceu ainda: as entradas sao os dois times e o historico
deles. O projeto ja teve um segundo modelo, que olhava o estado do mapa DURANTE
a partida (minuto, vantagem de ouro, torres) para dizer quem estava ganhando;
ele saiu junto das telas que o serviam. Esta e a previsao que restou, e e a que
tem valor pratico: dizer quem vence quando a partida ja esta em curso e util
para narrar, nao para decidir.

**Por que Bradley-Terry e nao um classificador com features.**

Sao 71 partidas com os dois times identificados, e so 44 delas tem historico
previo para os dois lados - o minimo para uma feature de forma existir sem
olhar o futuro. Um classificador com meia duzia de features sobre 44 linhas
produz um numero de acuracia com variancia enorme: uma partida a mais ou a
menos no teste mexe a metrica em quase 10 pontos. O numero pareceria resultado
sem ser.

Bradley-Terry e o modelo desenhado exatamente para este caso - comparacoes
par-a-par com poucas observacoes por participante. Ele estima uma FORCA por
time, e a probabilidade do confronto sai da diferenca entre as duas forcas. Na
pratica e uma regressao logistica sobre uma matriz de indicadores (+1 para o
time do lado A, -1 para o do lado B), o que traz duas propriedades que
importam aqui:

* **Regularizacao e um prior.** Com `C` pequeno, um time com duas partidas fica
  puxado para a forca media, e a previsao dele tende a 50%. E o comportamento
  certo: nao sabemos nada sobre ele ainda.
* **O intercepto e a vantagem de lado.** O modelo separa "o lado A ganha mais"
  de "este time e melhor", que sem isso ficariam somados no mesmo numero.

A validacao e temporal (walk-forward): para cada partida do periodo de teste,
as forcas sao reajustadas so com o que aconteceu ANTES dela. Um split
aleatorio deixaria o modelo estimar a forca de um time usando partidas
posteriores a que ele esta prevendo.

**Duas fontes de confronto, uma por jogo.** Dota 2 usa `dim_partida` /
`fato_partida_jogador`, que vem da OpenDota e so cobre Dota. Todo outro jogo
usa `agenda_partida`, que vem do ticker da Liquipedia (Fase 13) e cobre as 73
wikis do catalogo - mas so da o placar final, sem stats de jogador. O metodo
(Bradley-Terry) nao muda com a fonte; o que muda e o volume de historico e o
"por que" que da para mostrar (GPM/XPM/KDA existem so onde a OpenDota chega).
Ver `_carregar_confrontos` e `_carregar_equipes`, que fazem essa bifurcacao.

**Prior de ranking externo (Fase 15).** Para Counter-Strike ha uma terceira
entrada: o Regional Standings da Valve, em `ranking_externo`. Ele vira UMA
coluna a mais na regressao - a diferenca de rating (z-score do log-pontos)
entre os dois lados - e a regularizacao decide quanto peso dar a ela. O efeito
que importa: um time no topo do ranking com duas partidas coletadas para de
cair para ~50%, porque a coluna do prior o segura perto da posicao dele. Na
validacao walk-forward o prior e point-in-time (o ranking vigente na data da
partida, nunca um posterior). Para todo jogo sem `ranking_externo` a coluna
nao existe e o modelo e identico ao da Fase 14. Ver `_carregar_ratings_
externos`, `_ratings_em` e o parametro `ratings` de `_matriz`/`_ajustar`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sqlalchemy import Float, Integer, cast, func, select

from db.models import (
    AgendaPartida,
    DimEquipe,
    DimJogo,
    DimPartida,
    FatoPartidaJogador,
    RankingExterno,
)
from db.session import session_scope
from ml.modelos import SEMENTE

logger = logging.getLogger(__name__)

PASTA = Path(__file__).resolve().parent.parent / "data" / "modelos"
def arquivo_metricas(jogo: str) -> Path:
    """O artefato do modelo, UM POR JOGO.

    Era um arquivo so, e isso era um bug silencioso: `carregar_relatorio()` lia
    `metricas_confronto.json` sem olhar de qual jogo ele era, entao
    `/api/ml/confronto/relatorio?jogo=counterstrike` devolvia o relatorio do
    Dota 2 - com `"jogo": "dota2"` dentro da resposta - como se fosse de CS.
    Numeros certos respondendo a pergunta errada, que e o pior tipo de erro num
    projeto sobre integridade de dado.

    O nome entra no arquivo porque as forcas sao ajustadas sobre o historico de
    UM jogo: um `id_equipe` de Counter-Strike nao tem forca no ajuste do Dota, e
    a taxa base de um nao diz nada sobre o outro.
    """
    return PASTA / f"metricas_confronto_{jogo}.json"

#: Grade de regularizacao. `C` alto deixa as forcas livres e faz um time
#: invicto de duas partidas valer mais que um consistente de onze; `C` baixo
#: puxa todo mundo para a media e o modelo vira um chute em 50%.
#:
#: O valor NAO e escolhido olhando a metrica de teste - isso seria ajustar no
#: conjunto que deveria julgar o resultado. `_escolher_regularizacao` faz
#: validacao cruzada dentro da janela de treino, e o teste e usado uma vez so,
#: no fim.
GRADE_REGULARIZACAO = (2.0, 1.0, 0.5, 0.2, 0.08)

#: Fracao final da linha do tempo usada como teste na validacao walk-forward.
FRACAO_TESTE = 0.3

#: Minimo de partidas previas para os DOIS times entrarem numa avaliacao.
#: Sem historico nenhum a previsao e so a vantagem de lado, e medir isso
#: mediria o intercepto, nao o modelo.
MINIMO_HISTORICO = 1

#: Ranking externo usado como prior (Fase 15), por jogo. Counter-Strike tem o
#: Regional Standings da Valve; Valorant, o rating do vlr.gg. Um jogo fora deste
#: mapa (ou sem snapshot na tabela) simplesmente nao tem prior - o modelo volta
#: a ser o Bradley-Terry puro, sem coluna a mais.
FONTE_PRIOR_POR_JOGO: dict[str, str] = {
    "counterstrike": "valve",
    "valorant": "vlr",
}


def _fonte_prior(jogo: str) -> str | None:
    return FONTE_PRIOR_POR_JOGO.get(jogo)

#: Quantas partidas recentes entram na "forma" e no "saldo recente" de um time.
JANELA_FORMA = 6

#: As features de contexto que somam ao Bradley-Terry - uma coluna cada em
#: `_matriz`, todas SINAL de A menos B (0 = empatado), todas causais (so olham
#: o que veio antes do confronto). A regularizacao decide o peso de cada uma;
#: um jogo sem placar de serie (Dota) simplesmente tem `saldo_recente` = 0.
NOMES_FEATURES = ("forma_recente", "confronto_direto", "saldo_recente")


@dataclass(frozen=True)
class Confronto:
    id_partida: int
    data: datetime | None
    id_equipe_a: int
    id_equipe_b: int
    vitoria_a: bool
    liga: str | None
    #: Placar da serie (mapas/jogos/pontos, conforme o jogo). `None` quando a
    #: fonte nao publicou - so o vencedor. Ver `_preencher_saldo_placar`.
    placar_a: int | None = None
    placar_b: int | None = None


@dataclass
class Equipe:
    id_equipe: int
    nome: str
    tag: str | None
    logo_url: str | None
    partidas: int = 0
    vitorias: int = 0
    #: Coeficiente de Bradley-Terry. Zero e a media da liga.
    forca: float = 0.0
    gpm_medio: float | None = None
    xpm_medio: float | None = None
    kda_medio: float | None = None
    duracao_media_segundos: float | None = None
    #: Saldo medio de placar por confronto decidido, normalizado a [-1, 1]:
    #: +1 = so venceu por lavada, -1 = so perdeu de lavada. Independe do
    #: formato (2-0, 13-4 e 12-2 dao o mesmo +1). `None` para Dota (a fonte
    #: nao da placar de serie) e para jogo sem serie 1-contra-1.
    saldo_placar: float | None = None
    #: Posicao e pontos no ranking externo mais recente (Valve, so CS por
    #: enquanto). `None` quando a equipe nao aparece nele. Contexto para a
    #: tela - o efeito no modelo ja esta embutido em `forca` (Fase 15).
    posicao_ranking: int | None = None
    pontos_ranking: int | None = None
    #: Winrate nas ultimas `JANELA_FORMA` partidas, em %. `None` sem historico
    #: suficiente. Preenchido so na previsao (`prever`), nao no ranking.
    forma_recente: float | None = None

    @property
    def winrate(self) -> float:
        return 100.0 * self.vitorias / self.partidas if self.partidas else 0.0


@dataclass
class Fator:
    """Uma linha do 'por que' - o valor de cada lado e quem leva vantagem."""

    rotulo: str
    valor_a: float | None
    valor_b: float | None
    #: Positivo favorece A. `None` quando falta dado de um dos lados.
    diferenca: float | None
    unidade: str
    #: `True` quando o modelo aprendeu um peso para este fator (a forca, e as
    #: features de contexto cujo coeficiente nao ficou ~0). Os demais sao so
    #: leitura.
    peso_no_modelo: bool


@dataclass
class Contribuicao:
    """Uma parcela da log-odds de A vencer. A soma, pela sigmoide, e a
    probabilidade - e por isso a tela pode desenhar de onde saiu o numero."""

    rotulo: str
    #: Em log-odds. Positivo empurra para A, negativo para B.
    log_odds: float


@dataclass
class Previsao:
    equipe_a: Equipe
    equipe_b: Equipe
    probabilidade_a: float
    probabilidade_b: float
    #: Contribuicao da diferenca de forca, em log-odds.
    contribuicao_forca: float
    #: Contribuicao do lado (o intercepto), em log-odds.
    contribuicao_lado: float
    fatores: list[Fator] = field(default_factory=list)
    confrontos_diretos: int = 0
    vitorias_diretas_a: int = 0
    #: A decomposicao da log-odds em parcelas (forca, lado, forma, h2h, saldo).
    contribuicoes: list[Contribuicao] = field(default_factory=list)


def _carregar_confrontos(sessao, jogo: str = "dota2") -> list[Confronto]:
    """Confrontos com resultado, na fonte que existe para aquele jogo.

    **Dota 2 e os outros 72 usam fontes diferentes, e isso e proposital.** A
    OpenDota so cobre Dota - e da uma partida rica, com placar por jogador
    (GPM, XPM, KDA), que vira o "por que" na tela. A Liquipedia cobre todo o
    catalogo, mas so da o placar final: quem venceu, nada sobre como. Para
    Bradley-Terry os dois bastam igual - o metodo so precisa de quem venceu -
    entao Dota fica na fonte mais rica que ja tinha, e os demais ganham a
    fonte que os cobre.
    """
    if jogo != "dota2":
        return _carregar_confrontos_liquipedia(sessao, jogo)

    vencedor_radiant = (
        select(FatoPartidaJogador.id_partida, FatoPartidaJogador.vitoria)
        .where(FatoPartidaJogador.equipe == "radiant")
        .distinct()
        .subquery()
    )

    linhas = sessao.execute(
        select(
            DimPartida.id_partida,
            DimPartida.data_inicio,
            DimPartida.id_equipe_lado_a,
            DimPartida.id_equipe_lado_b,
            vencedor_radiant.c.vitoria,
            DimPartida.liga_nome,
        )
        .join(DimJogo, DimJogo.id_jogo == DimPartida.id_jogo)
        .join(vencedor_radiant, vencedor_radiant.c.id_partida == DimPartida.id_partida)
        .where(
            DimJogo.codigo == jogo,
            DimPartida.id_equipe_lado_a.is_not(None),
            DimPartida.id_equipe_lado_b.is_not(None),
            vencedor_radiant.c.vitoria.is_not(None),
        )
        .order_by(DimPartida.data_inicio)
    ).all()

    return [
        Confronto(
            id_partida=linha[0],
            data=linha[1],
            id_equipe_a=linha[2],
            id_equipe_b=linha[3],
            vitoria_a=bool(linha[4]),
            liga=linha[5],
        )
        for linha in linhas
    ]


def _carregar_confrontos_liquipedia(sessao, jogo: str) -> list[Confronto]:
    """Confrontos com resultado vindos do ticker da Liquipedia.

    Mesma forma de saida que a versao da OpenDota (`Confronto`) - o
    Bradley-Terry le a lista sem saber de qual fonte ela veio. `liga` aqui e o
    nome do torneio da Liquipedia, nao a liga da OpenDota, mas cumpre o mesmo
    papel (agrupar `ligas()`/`ranking(liga=...)`).
    """
    linhas = sessao.execute(
        select(
            AgendaPartida.id,
            AgendaPartida.inicio_previsto,
            AgendaPartida.id_equipe_a,
            AgendaPartida.id_equipe_b,
            AgendaPartida.vitoria_a,
            AgendaPartida.torneio,
            AgendaPartida.placar_a,
            AgendaPartida.placar_b,
        )
        .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
        .where(
            DimJogo.codigo == jogo,
            AgendaPartida.id_equipe_a.is_not(None),
            AgendaPartida.id_equipe_b.is_not(None),
            AgendaPartida.vitoria_a.is_not(None),
        )
        .order_by(AgendaPartida.inicio_previsto)
    ).all()

    return [
        Confronto(
            id_partida=linha[0],
            data=linha[1],
            id_equipe_a=linha[2],
            id_equipe_b=linha[3],
            vitoria_a=bool(linha[4]),
            liga=linha[5],
            placar_a=linha[6],
            placar_b=linha[7],
        )
        for linha in linhas
    ]


def _preencher_partidas_liquipedia(
    sessao, jogo: str, equipes: dict[int, Equipe]
) -> None:
    """Conta quantos confrontos decididos cada equipe tem, sem OpenDota.

    Sem stats de jogador, `partidas` e o unico numero de volume que da para
    calcular para estes jogos - mas ele PRECISA ser calculado aqui: sem isto
    toda equipe fica com `partidas=0`, `winrate` sai sempre 0%, e o filtro
    final de `estado()` (`if equipe.partidas`) descartaria TODAS as equipes -
    o ranking viria vazio mesmo com confrontos reais no banco.
    """
    for coluna in (AgendaPartida.id_equipe_a, AgendaPartida.id_equipe_b):
        for id_equipe, contagem in sessao.execute(
            select(coluna, func.count())
            .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
            .where(
                DimJogo.codigo == jogo,
                coluna.is_not(None),
                AgendaPartida.vitoria_a.is_not(None),
            )
            .group_by(coluna)
        ):
            equipe = equipes.get(id_equipe)
            if equipe is not None:
                equipe.partidas += contagem


def _preencher_ranking_externo(sessao, jogo: str, equipes: dict[int, Equipe]) -> None:
    """Anexa posicao e pontos do ranking externo MAIS RECENTE a cada equipe.

    So contexto de tela - o efeito no modelo ja esta em `forca`. `None` para
    equipe fora do ranking, e no-op inteiro para jogo sem `ranking_externo`.
    """
    fonte = _fonte_prior(jogo)
    if fonte is None:
        return
    ultima = sessao.scalar(
        select(func.max(RankingExterno.data_referencia))
        .join(DimJogo, DimJogo.id_jogo == RankingExterno.id_jogo)
        .where(DimJogo.codigo == jogo, RankingExterno.fonte == fonte)
    )
    if ultima is None:
        return

    for id_equipe, posicao, pontos in sessao.execute(
        select(
            RankingExterno.id_equipe, RankingExterno.posicao, RankingExterno.pontos
        ).where(
            RankingExterno.fonte == fonte,
            RankingExterno.data_referencia == ultima,
            RankingExterno.id_equipe.is_not(None),
        )
    ):
        equipe = equipes.get(id_equipe)
        if equipe is not None:
            equipe.posicao_ranking = int(posicao)
            equipe.pontos_ranking = int(pontos) if pontos is not None else None


def _preencher_saldo_placar(sessao, jogo: str, equipes: dict[int, Equipe]) -> None:
    """Media do saldo de placar por confronto, normalizada a [-1, 1].

    Winrate ja diz quantas o time venceu; isto diz COMO. Um 2-0 e um 2-1
    contam igual no winrate, mas o primeiro e dominio e o segundo e sorte de
    mapa - `(placar_meu - placar_dele) / (placar_meu + placar_dele)` separa os
    dois sem depender do formato: 2-0, 13-4 e 12-2 dao +1 igual.

    So faz sentido onde a serie e 1-contra-1 (`unidade_placar` do jogo nao e
    `None`) - em battle royale o "placar" e colocacao numa lobby, nao ha saldo.
    """
    from etl.wikis import unidade_placar

    if unidade_placar(jogo) is None:
        return

    linhas = sessao.execute(
        select(
            AgendaPartida.id_equipe_a,
            AgendaPartida.id_equipe_b,
            AgendaPartida.placar_a,
            AgendaPartida.placar_b,
        )
        .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
        .where(
            DimJogo.codigo == jogo,
            AgendaPartida.vitoria_a.is_not(None),
            AgendaPartida.id_equipe_a.is_not(None),
            AgendaPartida.id_equipe_b.is_not(None),
            AgendaPartida.placar_a.is_not(None),
            AgendaPartida.placar_b.is_not(None),
        )
    ).all()

    acumulado: dict[int, list[float]] = {}
    for id_a, id_b, pa, pb in linhas:
        total = (pa or 0) + (pb or 0)
        if total <= 0:
            continue
        saldo_a = (pa - pb) / total
        acumulado.setdefault(id_a, []).append(saldo_a)
        acumulado.setdefault(id_b, []).append(-saldo_a)

    for id_equipe, saldos in acumulado.items():
        equipe = equipes.get(id_equipe)
        if equipe is not None and saldos:
            equipe.saldo_placar = sum(saldos) / len(saldos)


def _carregar_equipes(sessao, jogo: str = "dota2") -> dict[int, Equipe]:
    """As equipes do jogo, com o desempenho medio quando a fonte tem.

    As medias de GPM/XPM/KDA saem do fato de jogador da OpenDota, que so
    existe para Dota 2 - o time nao tem GPM proprio, tem o GPM dos cinco que
    jogaram por ele. Para os outros jogos esses campos ficam `None` (o padrao
    do dataclass `Equipe`): a Liquipedia da o placar final, nao telemetria por
    jogador, e mostrar um numero inventado seria pior que mostrar um travessao
    - a tela ja trata `None` como "sem dado" em vez de "zero".
    """
    equipes = {
        linha[0]: Equipe(
            id_equipe=linha[0], nome=linha[1], tag=linha[2], logo_url=linha[3]
        )
        for linha in sessao.execute(
            select(
                DimEquipe.id_equipe, DimEquipe.nome, DimEquipe.tag, DimEquipe.logo_url
            )
            .join(DimJogo, DimJogo.id_jogo == DimEquipe.id_jogo)
            .where(DimJogo.codigo == jogo)
        )
    }

    _preencher_ranking_externo(sessao, jogo, equipes)

    if jogo != "dota2":
        _preencher_partidas_liquipedia(sessao, jogo, equipes)
        _preencher_saldo_placar(sessao, jogo, equipes)
        return equipes

    # O lado do fato ("radiant"/"dire") liga o jogador a equipe da partida.
    for lado, coluna in (
        ("radiant", DimPartida.id_equipe_lado_a),
        ("dire", DimPartida.id_equipe_lado_b),
    ):
        for linha in sessao.execute(
            select(
                coluna,
                func.avg(FatoPartidaJogador.economia_por_minuto),
                func.avg(FatoPartidaJogador.experiencia_por_minuto),
                func.avg(
                    (
                        cast(FatoPartidaJogador.kills, Float)
                        + cast(FatoPartidaJogador.assists, Float)
                    )
                    / func.greatest(cast(FatoPartidaJogador.deaths, Float), 1.0)
                ),
                func.avg(FatoPartidaJogador.duracao_partida_segundos),
                func.count(func.distinct(FatoPartidaJogador.id_partida)),
            )
            .join(DimPartida, DimPartida.id_partida == FatoPartidaJogador.id_partida)
            .where(coluna.is_not(None), FatoPartidaJogador.equipe == lado)
            .group_by(coluna)
        ):
            equipe = equipes.get(linha[0])
            if equipe is None:
                continue

            # Media ponderada com o que ja veio do outro lado: um time joga de
            # radiant em umas partidas e de dire em outras.
            anteriores = equipe.partidas
            novas = linha[5] or 0
            total = anteriores + novas
            if not total:
                continue

            def combinar(atual: float | None, novo: Any) -> float | None:
                if novo is None:
                    return atual
                novo = float(novo)
                if atual is None:
                    return novo
                return (atual * anteriores + novo * novas) / total

            equipe.gpm_medio = combinar(equipe.gpm_medio, linha[1])
            equipe.xpm_medio = combinar(equipe.xpm_medio, linha[2])
            equipe.kda_medio = combinar(equipe.kda_medio, linha[3])
            equipe.duracao_media_segundos = combinar(
                equipe.duracao_media_segundos, linha[4]
            )
            equipe.partidas = total

    return equipes


#: Um snapshot do ranking externo: a data em que valeu, e a forca relativa
#: (z-score do log-pontos, dentro do snapshot) de cada equipe casada.
Snapshot = tuple[date, dict[int, float]]


def _carregar_ratings_externos(sessao, jogo: str) -> list[Snapshot]:
    """Todos os snapshots do ranking externo do jogo, do mais antigo ao recente.

    O rating e o z-score de `log(pontos)` DENTRO de cada snapshot: um numero
    adimensional que diz "quantos desvios acima da media da lista este time
    esta". `log` porque a pontuacao cai de forma quase exponencial (2011 no
    topo, ~400 na cauda); z-score porque a escala de pontos da Valve nao tem
    significado fora da lista dela.

    Vazio para todo jogo sem linha em `ranking_externo` - e a maioria. Nesse
    caso o resto do modulo ignora o prior e nada muda em relacao a Fase 14.
    """
    fonte = _fonte_prior(jogo)
    if fonte is None:
        return []
    linhas = sessao.execute(
        select(
            RankingExterno.data_referencia,
            RankingExterno.id_equipe,
            RankingExterno.pontos,
        )
        .join(DimJogo, DimJogo.id_jogo == RankingExterno.id_jogo)
        .where(
            DimJogo.codigo == jogo,
            RankingExterno.fonte == fonte,
            RankingExterno.id_equipe.is_not(None),
            RankingExterno.pontos.is_not(None),
            RankingExterno.pontos > 0,
        )
        .order_by(RankingExterno.data_referencia)
    ).all()

    por_data: dict[date, dict[int, float]] = {}
    for data_ref, id_equipe, pontos in linhas:
        por_data.setdefault(data_ref, {})[int(id_equipe)] = float(np.log(pontos))

    snapshots: list[Snapshot] = []
    for data_ref in sorted(por_data):
        brutos = por_data[data_ref]
        valores = np.fromiter(brutos.values(), dtype=float)
        media, desvio = float(valores.mean()), float(valores.std())
        if desvio == 0.0:
            continue
        snapshots.append(
            (data_ref, {ide: (v - media) / desvio for ide, v in brutos.items()})
        )
    return snapshots


def _ratings_em(snapshots: list[Snapshot], quando: date | None) -> dict[int, float]:
    """O snapshot vigente numa data - o mais recente com `data_referencia` <=
    `quando`. Com `quando=None` (o modelo final, nao a validacao), usa o ultimo.

    Point-in-time de proposito: prever uma partida de julho com o ranking de
    agosto seria vazar resultado de agosto na previsao de julho.
    """
    if not snapshots:
        return {}
    if quando is None:
        return snapshots[-1][1]
    vigente: dict[int, float] = {}
    for data_ref, ratings in snapshots:
        if data_ref <= quando:
            vigente = ratings
        else:
            break
    return vigente


def _do_time(historico: list[Confronto], id_equipe: int):
    """`(venceu?, confronto)` de cada partida do time no historico, em ordem."""
    for c in historico:
        if c.id_equipe_a == id_equipe:
            yield c.vitoria_a, c
        elif c.id_equipe_b == id_equipe:
            yield (not c.vitoria_a), c


def _forma(historico: list[Confronto], id_equipe: int) -> float:
    """Winrate nas ultimas `JANELA_FORMA` partidas, centrado em 0.5 (0 = 50%).

    `0.0` (neutro) com menos de duas partidas: uma vitoria isolada nao e forma.
    """
    jogos = list(_do_time(historico, id_equipe))[-JANELA_FORMA:]
    if len(jogos) < 2:
        return 0.0
    return sum(1 for venceu, _ in jogos if venceu) / len(jogos) - 0.5


def _h2h(historico: list[Confronto], a: int, b: int) -> float:
    """Vantagem de A no confronto direto, encolhida por amostra (Beta(1,1)).

    `(vitorias_a + 1) / (total + 2) - 0.5`: dois jogos 2-0 dao +0.25, nao +0.5;
    nunca se jogaram da 0. Sem o encolhimento, um unico encontro mandaria a
    previsao para 0/100.
    """
    diretos = [c for c in historico if {c.id_equipe_a, c.id_equipe_b} == {a, b}]
    if not diretos:
        return 0.0
    vitorias_a = sum(1 for c in diretos if (c.id_equipe_a == a) == c.vitoria_a)
    return (vitorias_a + 1) / (len(diretos) + 2) - 0.5


def _saldo_recente(historico: list[Confronto], id_equipe: int) -> float:
    """Margem media de placar nas ultimas partidas, normalizada a [-1, 1].

    `0.0` quando a fonte nao da placar de serie (Dota) - a coluna existe, so
    nao carrega sinal nesse jogo.
    """
    margens: list[float] = []
    for _, c in list(_do_time(historico, id_equipe))[-JANELA_FORMA:]:
        if c.placar_a is None or c.placar_b is None:
            continue
        total = c.placar_a + c.placar_b
        if not total:
            continue
        meu, seu = (
            (c.placar_a, c.placar_b)
            if c.id_equipe_a == id_equipe
            else (c.placar_b, c.placar_a)
        )
        margens.append((meu - seu) / total)
    return sum(margens) / len(margens) if margens else 0.0


def _features_do_confronto(historico: list[Confronto], a: int, b: int) -> list[float]:
    """As `NOMES_FEATURES` para o confronto A x B, a partir de `historico`.

    Usado dos dois lados: no treino `historico` e `confrontos[:i]` (causal); na
    previsao ao vivo e todo o historico ate hoje.
    """
    return [
        _forma(historico, a) - _forma(historico, b),
        _h2h(historico, a, b),
        _saldo_recente(historico, a) - _saldo_recente(historico, b),
    ]


def _features_temporais(confrontos: list[Confronto]) -> list[list[float]]:
    """A matriz de features, uma linha por confronto, olhando so o que veio antes.

    A causalidade e o ponto: `confrontos[i]` ve `confrontos[:i]` e nada mais.
    Sem isso, a "forma" de um time incluiria a partida que ela esta prevendo, e
    a validacao walk-forward viraria mentira.
    """
    return [
        _features_do_confronto(
            confrontos[:i], alvo.id_equipe_a, alvo.id_equipe_b
        )
        for i, alvo in enumerate(confrontos)
    ]


def _matriz(
    confrontos: list[Confronto],
    indices: dict[int, int],
    ratings: dict[int, float] | None = None,
    features: list[list[float]] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Matriz de indicadores: +1 para o time do lado A, -1 para o do lado B.

    E a forma padrao de escrever Bradley-Terry como regressao logistica. Cada
    coluna de time tem por coeficiente a forca dele.

    Colunas a mais, na ordem: as `features` de contexto (forma, confronto
    direto, saldo) e, por ultimo, a diferenca de rating externo (`ratings`,
    Fase 15). A regularizacao aprende o peso de cada uma junto das forcas - e
    para um time de poucas partidas, cuja coluna encolhe para ~0, sao esses
    termos que sobram dizendo algo sobre ele. O rating fica SEMPRE por ultimo:
    `_ajustar` le `coef_[-1]` para ele.
    """
    n_feat = len(features[0]) if features else 0
    n_rating = 1 if ratings else 0
    X = np.zeros((len(confrontos), len(indices) + n_feat + n_rating))
    y = np.zeros(len(confrontos), dtype=int)

    for linha, confronto in enumerate(confrontos):
        X[linha, indices[confronto.id_equipe_a]] = 1.0
        X[linha, indices[confronto.id_equipe_b]] = -1.0
        if features:
            X[linha, len(indices) : len(indices) + n_feat] = features[linha]
        if ratings:
            X[linha, -1] = ratings.get(confronto.id_equipe_a, 0.0) - ratings.get(
                confronto.id_equipe_b, 0.0
            )
        y[linha] = 1 if confronto.vitoria_a else 0

    return X, y


def _coef_clipado(
    modelo: LogisticRegression, inicio_feat: int, n_feat: int
) -> np.ndarray:
    """Os coeficientes do modelo com as features de contexto travadas em >= 0.

    A direcao dessas features e conhecida (ver `_ajustar`); um coeficiente
    negativo e ruido. Aplicado ANTES de medir a perda na CV, para o `C`
    escolhido ser o do modelo que de fato roda.
    """
    coef = modelo.coef_[0].copy()
    for k in range(n_feat):
        coef[inicio_feat + k] = max(0.0, coef[inicio_feat + k])
    return coef


def _proba(X: np.ndarray, coef: np.ndarray, intercepto: float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-(X @ coef + intercepto)))


def _escolher_regularizacao(
    confrontos: list[Confronto],
    ratings: dict[int, float] | None = None,
    features: list[list[float]] | None = None,
) -> float:
    """Escolhe `C` por validacao cruzada DENTRO da janela recebida.

    Recebe so o treino. Rodar isto sobre o conjunto inteiro e depois reportar a
    metrica de teste daria um numero otimista: o valor de `C` ja teria visto as
    partidas que ele e julgado a prever.
    """
    ids = sorted({c.id_equipe_a for c in confrontos} | {c.id_equipe_b for c in confrontos})
    indices = {id_equipe: posicao for posicao, id_equipe in enumerate(ids)}
    X, y = _matriz(confrontos, indices, ratings, features)
    n_feat = len(features[0]) if features else 0
    inicio_feat = len(indices)

    if len(set(y)) < 2 or len(y) < 20:
        return 0.5

    melhor_c, melhor_perda = 0.5, float("inf")
    dobras = StratifiedKFold(n_splits=4, shuffle=True, random_state=SEMENTE)

    for candidato in GRADE_REGULARIZACAO:
        perdas: list[float] = []
        for treino, validacao in dobras.split(X, y):
            if len(set(y[treino])) < 2 or len(set(y[validacao])) < 2:
                continue
            modelo = LogisticRegression(
                C=candidato, max_iter=2000, random_state=SEMENTE
            )
            modelo.fit(X[treino], y[treino])
            coef = _coef_clipado(modelo, inicio_feat, n_feat)
            perdas.append(
                log_loss(
                    y[validacao],
                    _proba(X[validacao], coef, float(modelo.intercept_[0])),
                    labels=[0, 1],
                )
            )

        if perdas and float(np.mean(perdas)) < melhor_perda:
            melhor_perda, melhor_c = float(np.mean(perdas)), candidato

    return melhor_c


def _ajustar(
    confrontos: list[Confronto],
    regularizacao: float | None = None,
    ratings: dict[int, float] | None = None,
    features: list[list[float]] | None = None,
) -> tuple[dict[int, float], float, float, list[float]]:
    """Devolve: forca de cada equipe, vantagem do lado A (log-odds), peso do
    prior externo (0.0 sem prior) e o peso aprendido de cada feature de contexto
    (`NOMES_FEATURES`, na ordem; lista vazia sem features).

    Com `ratings`, a forca guardada de cada time ja SOMA o termo do prior
    (`peso * rating`): quem consome `forca` depois - `_probabilidade`,
    `prever`, o ranking - nao precisa saber que o prior existe. Ja as features
    de contexto NAO entram na forca: elas dependem do adversario e da data, e
    sao aplicadas na hora da previsao.
    """
    ids = sorted({c.id_equipe_a for c in confrontos} | {c.id_equipe_b for c in confrontos})
    indices = {id_equipe: posicao for posicao, id_equipe in enumerate(ids)}

    X, y = _matriz(confrontos, indices, ratings, features)
    n_feat = len(features[0]) if features else 0

    # Uma classe so (todo mundo ganhou de um lado) nao tem o que ajustar.
    if len(set(y)) < 2:
        return {id_equipe: 0.0 for id_equipe in ids}, 0.0, 0.0, [0.0] * n_feat

    modelo = LogisticRegression(
        C=regularizacao
        if regularizacao is not None
        else _escolher_regularizacao(confrontos, ratings, features),
        max_iter=2000,
        random_state=SEMENTE,
    )
    modelo.fit(X, y)

    inicio_feat = len(indices)
    # As features de contexto tem DIRECAO conhecida: quem esta em melhor forma,
    # com vantagem no confronto direto ou vencendo por margens maiores tende a
    # ganhar - nunca o contrario. Um coeficiente negativo e sobreajuste a ruido
    # numa amostra de poucas dezenas; a leitura honesta e "essa feature nao
    # mostrou sinal para este jogo", entao ele vira 0.
    coef = _coef_clipado(modelo, inicio_feat, n_feat)
    peso_externo = float(coef[-1]) if ratings else 0.0
    pesos_features = [float(coef[inicio_feat + k]) for k in range(n_feat)]
    forcas = {
        id_equipe: float(modelo.coef_[0][posicao])
        + peso_externo * (ratings.get(id_equipe, 0.0) if ratings else 0.0)
        for id_equipe, posicao in indices.items()
    }
    return forcas, float(modelo.intercept_[0]), peso_externo, pesos_features


def _probabilidade(
    forca_a: float, forca_b: float, lado: float, contexto: float = 0.0
) -> float:
    """P(A vence) = sigmoide(diferenca de forca + vantagem de lado + contexto).

    `contexto` e a soma `peso_k * feature_k` das features de A x B (forma,
    confronto direto, saldo) - zero quando o modelo nao tem features.
    """
    return float(1.0 / (1.0 + np.exp(-((forca_a - forca_b) + lado + contexto))))


def _avaliar_walk_forward(
    confrontos: list[Confronto], snapshots: list[Snapshot] | None = None
) -> dict[str, Any]:
    """Reajusta as forcas antes de cada partida do periodo de teste.

    O corte e temporal: nenhuma partida do teste influencia a forca com que ela
    propria e prevista. E mais caro que um split unico - reajusta o modelo a
    cada partida - mas com 71 confrontos isso custa milissegundos, e e a unica
    forma de o numero significar alguma coisa.

    Com `snapshots` (o ranking externo, Fase 15), o prior de cada reajuste usa
    o snapshot VIGENTE na data da partida-alvo - nunca um posterior. E o que
    mantem a validacao honesta: o ranking de agosto reflete resultados de
    agosto, e usa-lo para prever julho seria vazamento.
    """
    snapshots = snapshots or []
    features = _features_temporais(confrontos)
    corte = int(len(confrontos) * (1 - FRACAO_TESTE))
    probabilidades: list[float] = []
    reais: list[int] = []
    avaliadas: list[int] = []

    for posicao in range(corte, len(confrontos)):
        historico = confrontos[:posicao]
        alvo = confrontos[posicao]

        vistos_a = sum(
            1 for c in historico if alvo.id_equipe_a in (c.id_equipe_a, c.id_equipe_b)
        )
        vistos_b = sum(
            1 for c in historico if alvo.id_equipe_b in (c.id_equipe_a, c.id_equipe_b)
        )
        if vistos_a < MINIMO_HISTORICO or vistos_b < MINIMO_HISTORICO:
            continue

        feat_hist = features[:posicao]
        # O prior e o ranking vigente na data da partida - nao o de hoje.
        ratings = _ratings_em(snapshots, alvo.data.date() if alvo.data else None)
        # `C` sai da validacao cruzada dentro do historico, nunca do teste.
        forcas, lado, _, pesos_feat = _ajustar(
            historico,
            _escolher_regularizacao(historico, ratings, feat_hist),
            ratings,
            feat_hist,
        )
        # `features[posicao]` foi montada de `confrontos[:posicao]` = o historico:
        # e exatamente a feature PRE-partida do alvo, sem vazamento.
        contexto = sum(p * f for p, f in zip(pesos_feat, features[posicao]))
        probabilidades.append(
            _probabilidade(
                forcas.get(alvo.id_equipe_a, 0.0),
                forcas.get(alvo.id_equipe_b, 0.0),
                lado,
                contexto,
            )
        )
        reais.append(1 if alvo.vitoria_a else 0)
        avaliadas.append(alvo.id_partida)

    return _metricas(probabilidades, reais)


def _metricas(probabilidades: list[float], reais: list[int]) -> dict[str, Any]:
    """As metricas da validacao, a partir das probabilidades e do que ocorreu.

    Separada do laco walk-forward para ser testavel sozinha: o que se afirma
    sobre "o modelo supera o chute?" e uma comparacao entre dois numeros deste
    dicionario, e ela ja saiu errada uma vez por causa de arredondamento.
    """
    if len(probabilidades) < 5 or len(set(reais)) < 2:
        return {
            "avaliadas": len(probabilidades),
            "suficiente": False,
            "motivo": (
                "Partidas de menos no periodo de teste com historico previo para os "
                "dois times. Colete mais partidas para a validacao valer."
            ),
        }

    previsto = [1 if p >= 0.5 else 0 for p in probabilidades]
    taxa_base = sum(reais) / len(reais)

    return {
        "avaliadas": len(probabilidades),
        "suficiente": True,
        "acuracia": float(accuracy_score(reais, previsto)),
        "roc_auc": float(roc_auc_score(reais, probabilidades)),
        "log_loss": float(log_loss(reais, probabilidades, labels=[0, 1])),
        "brier": float(brier_score_loss(reais, probabilidades)),
        # SEM arredondar, e isso e correcao de bug, nao estilo. A acuracia ia
        # em precisao cheia e a taxa base em 4 casas, e quem decide se "o
        # modelo supera o chute" - na CLI e na tela - compara as duas. Um
        # empate virava vitoria ou derrota conforme o lado para o qual a quinta
        # casa arredondou: Call of Duty acertava 11 de 14 (0.785714...) contra
        # base 0.7857 e era anunciado como preditivo, com ROC-AUC de 0.182 -
        # pior que aleatorio. Brawl Stars, com o mesmo empate, arredondou para
        # cima e era corretamente reprovado. Em precisao cheia um empate e um
        # empate, e empate nao supera.
        "taxa_base": float(taxa_base),
        # Com poucas dezenas de partidas, o intervalo importa mais que o ponto.
        # E o erro padrao binomial da propria acuracia.
        "margem_erro": round(
            1.96
            * float(np.sqrt(accuracy_score(reais, previsto) * (1 - accuracy_score(reais, previsto)) / len(reais))),
            4,
        ),
    }


def _resumo_prior(
    snapshots: list[Snapshot],
    ratings_finais: dict[int, float],
    forcas: dict[int, float],
    peso: float,
    fonte: str,
) -> dict[str, Any] | None:
    """O bloco do relatorio que descreve o prior externo - ou `None` se nao ha.

    `None` e o estado de todo jogo sem ranking externo: a tela e a API sabem
    que, sem este bloco, o modelo e o Bradley-Terry puro.
    """
    if not snapshots:
        return None
    cobertas = [ide for ide in ratings_finais if ide in forcas]
    return {
        "fonte": fonte,
        "peso": round(peso, 4),
        "snapshots": len(snapshots),
        "data_mais_recente": snapshots[-1][0].isoformat(),
        "equipes_no_ranking": len(ratings_finais),
        "equipes_no_ranking_com_confronto": len(cobertas),
    }


def ajustar_e_salvar(jogo: str = "dota2") -> dict[str, Any]:
    """Ajusta as forcas sobre todo o historico e grava o relatorio."""
    with session_scope() as sessao:
        confrontos = _carregar_confrontos(sessao, jogo)
        equipes = _carregar_equipes(sessao, jogo)
        snapshots = _carregar_ratings_externos(sessao, jogo)

    if len(confrontos) < 10:
        comando = (
            "cli.py collect opendota"
            if jogo == "dota2"
            else f"cli.py collect liquipedia --wiki {jogo}"
        )
        raise ValueError(
            f"confrontos de menos para ajustar ({len(confrontos)}). "
            f"Colete mais partidas com `{comando}` - repetido ao longo do tempo, "
            "porque o ticker da Liquipedia so guarda uma janela recente."
        )

    ratings_finais = _ratings_em(snapshots, None)
    features = _features_temporais(confrontos)
    regularizacao = _escolher_regularizacao(confrontos, ratings_finais, features)
    forcas, lado, peso_externo, pesos_features = _ajustar(
        confrontos, regularizacao, ratings_finais, features
    )

    for confronto in confrontos:
        for id_equipe, venceu in (
            (confronto.id_equipe_a, confronto.vitoria_a),
            (confronto.id_equipe_b, not confronto.vitoria_a),
        ):
            equipe = equipes.get(id_equipe)
            if equipe is not None and venceu:
                equipe.vitorias += 1

    for id_equipe, forca in forcas.items():
        if id_equipe in equipes:
            equipes[id_equipe].forca = forca

    validacao = _avaliar_walk_forward(confrontos, snapshots)

    PASTA.mkdir(parents=True, exist_ok=True)
    relatorio = {
        "ajustado_em": datetime.now(timezone.utc).isoformat(),
        "jogo": jogo,
        "metodo": (
            "Bradley-Terry regularizado (regressão logística sobre indicadores "
            "de time) + features de contexto pré-partida"
        ),
        "regularizacao_C": regularizacao,
        "grade_regularizacao": list(GRADE_REGULARIZACAO),
        "confrontos": len(confrontos),
        "equipes": len(forcas),
        "vantagem_lado_a": round(lado, 4),
        "probabilidade_lado_a_entre_iguais": round(_probabilidade(0.0, 0.0, lado), 4),
        # O peso que a regressao deu a cada feature de contexto (log-odds por
        # unidade da feature). Perto de zero = a regularizacao nao viu sinal
        # nela para este jogo.
        "pesos_features": {
            nome: round(peso, 4)
            for nome, peso in zip(NOMES_FEATURES, pesos_features)
        },
        "janela_forma": JANELA_FORMA,
        "primeira_partida": confrontos[0].data.isoformat() if confrontos[0].data else None,
        "ultima_partida": confrontos[-1].data.isoformat() if confrontos[-1].data else None,
        "validacao": validacao,
        "prior_externo": _resumo_prior(
            snapshots, ratings_finais, forcas, peso_externo, _fonte_prior(jogo) or ""
        ),
        "forcas": {
            str(id_equipe): round(forca, 4) for id_equipe, forca in forcas.items()
        },
    }

    arquivo_metricas(jogo).write_text(
        json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(
        "forcas ajustadas",
        extra={"confrontos": len(confrontos), "equipes": len(forcas)},
    )
    return relatorio


def carregar_relatorio(jogo: str = "dota2") -> dict[str, Any] | None:
    """O relatorio do jogo pedido, ou `None` se ele nunca foi ajustado."""
    caminho = arquivo_metricas(jogo)
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def jogos_com_modelo() -> list[str]:
    """Os codigos de jogo que ja tem um modelo de confronto ajustado.

    Um por arquivo `metricas_confronto_<jogo>.json`. Serve ao assistente: ele
    precisa saber para quais jogos "quem ganha o confronto?" tem resposta com
    modelo, e para quais ainda nao.
    """
    if not PASTA.exists():
        return []
    return sorted(
        caminho.stem.removeprefix("metricas_confronto_")
        for caminho in PASTA.glob("metricas_confronto_*.json")
    )


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------


def _fator(
    rotulo: str,
    a: float | None,
    b: float | None,
    unidade: str,
    peso: bool = False,
    casas: int = 1,
) -> Fator:
    diferenca = round(a - b, casas) if a is not None and b is not None else None
    return Fator(
        rotulo=rotulo,
        valor_a=round(a, casas) if a is not None else None,
        valor_b=round(b, casas) if b is not None else None,
        diferenca=diferenca,
        unidade=unidade,
        peso_no_modelo=peso,
    )


def estado(jogo: str = "dota2") -> tuple[dict[int, Equipe], dict[str, Any]]:
    """Equipes com forca preenchida, e o relatorio do ultimo ajuste."""
    relatorio = carregar_relatorio(jogo)
    if relatorio is None:
        raise FileNotFoundError(
            f"as forcas de {jogo!r} nao foram ajustadas. Rode "
            f"`python cli.py train-confronto --jogo {jogo}` - e note que o ajuste "
            "precisa de partidas COM RESULTADO: para Dota 2 elas vem da OpenDota, "
            "para os demais jogos vem do ticker da Liquipedia "
            f"(`cli.py collect liquipedia --wiki {jogo}`, coletado ao longo do tempo)."
        )

    with session_scope() as sessao:
        equipes = _carregar_equipes(sessao, jogo)
        confrontos = _carregar_confrontos(sessao, jogo)

    for confronto in confrontos:
        for id_equipe, venceu in (
            (confronto.id_equipe_a, confronto.vitoria_a),
            (confronto.id_equipe_b, not confronto.vitoria_a),
        ):
            equipe = equipes.get(id_equipe)
            if equipe is not None and venceu:
                equipe.vitorias += 1

    for chave, forca in relatorio["forcas"].items():
        equipe = equipes.get(int(chave))
        if equipe is not None:
            equipe.forca = forca

    # Equipe sem partida no recorte nao entra: ela existe na dimensao porque
    # apareceu em alguma coleta, mas nao ha o que dizer sobre ela.
    return {id_e: e for id_e, e in equipes.items() if e.partidas}, relatorio


def prever(id_equipe_a: int, id_equipe_b: int, jogo: str = "dota2") -> Previsao:
    """Probabilidade de o time A vencer o time B, com os fatores por tras."""
    equipes, relatorio = estado(jogo)

    if id_equipe_a not in equipes or id_equipe_b not in equipes:
        faltando = [
            id_e for id_e in (id_equipe_a, id_equipe_b) if id_e not in equipes
        ]
        raise KeyError(f"equipe(s) sem partidas coletadas: {faltando}")
    if id_equipe_a == id_equipe_b:
        raise ValueError("os dois lados sao a mesma equipe")

    a, b = equipes[id_equipe_a], equipes[id_equipe_b]
    lado = float(relatorio["vantagem_lado_a"])

    with session_scope() as sessao:
        confrontos = _carregar_confrontos(sessao, jogo)

    # As features de contexto sao calculadas AGORA, do historico inteiro ate
    # hoje - `_carregar_confrontos` ja vem ordenado por data.
    pesos_features = [
        float((relatorio.get("pesos_features") or {}).get(nome, 0.0))
        for nome in NOMES_FEATURES
    ]
    features_agora = _features_do_confronto(confrontos, id_equipe_a, id_equipe_b)
    contexto = sum(p * f for p, f in zip(pesos_features, features_agora))

    probabilidade = _probabilidade(a.forca, b.forca, lado, contexto)

    # `_forma` devolve winrate - 0.5; a tela mostra em % (o +50 desfaz o centro).
    fa, fb = _forma(confrontos, id_equipe_a), _forma(confrontos, id_equipe_b)
    a.forma_recente = round((fa + 0.5) * 100, 1) if fa else None
    b.forma_recente = round((fb + 0.5) * 100, 1) if fb else None

    diretos = [
        c
        for c in confrontos
        if {c.id_equipe_a, c.id_equipe_b} == {id_equipe_a, id_equipe_b}
    ]
    vitorias_diretas_a = sum(
        1
        for c in diretos
        if (c.id_equipe_a == id_equipe_a and c.vitoria_a)
        or (c.id_equipe_b == id_equipe_a and not c.vitoria_a)
    )

    contribuicoes = _contribuicoes(
        a.forca - b.forca, lado, pesos_features, features_agora
    )

    return Previsao(
        equipe_a=a,
        equipe_b=b,
        probabilidade_a=round(probabilidade, 4),
        probabilidade_b=round(1 - probabilidade, 4),
        contribuicao_forca=round(a.forca - b.forca, 4),
        contribuicao_lado=round(lado, 4),
        confrontos_diretos=len(diretos),
        vitorias_diretas_a=vitorias_diretas_a,
        fatores=_fatores_da_previsao(
            a, b, _unidade_placar(jogo), features_agora, pesos_features
        ),
        contribuicoes=contribuicoes,
    )


#: Como cada feature de contexto se le na tela.
_ROTULO_FEATURE = {
    "forma_recente": "Forma recente",
    "confronto_direto": "Confronto direto",
    "saldo_recente": "Saldo de placar recente",
}


def _contribuicoes(
    dif_forca: float,
    lado: float,
    pesos_features: list[float],
    features_agora: list[float],
) -> list["Contribuicao"]:
    """Quanto cada parte empurra a log-odds de A vencer - a soma passa pela
    sigmoide e da a probabilidade. E o 'por que' com numero, nao so rotulo."""
    itens = [
        Contribuicao("Força estimada", round(dif_forca, 4)),
        Contribuicao("Vantagem de lado", round(lado, 4)),
    ]
    for nome, peso, feat in zip(NOMES_FEATURES, pesos_features, features_agora):
        parcela = peso * feat
        if abs(parcela) < 1e-4:
            continue
        itens.append(
            Contribuicao(_ROTULO_FEATURE.get(nome, nome), round(parcela, 4))
        )
    return itens


def _unidade_placar(jogo: str) -> str | None:
    from etl.wikis import unidade_placar

    return unidade_placar(jogo)


def _fatores_da_previsao(
    a: Equipe,
    b: Equipe,
    unidade_placar: str | None = None,
    features_agora: list[float] | None = None,
    pesos_features: list[float] | None = None,
) -> list[Fator]:
    """Os fatores do 'por que', so os que fazem sentido para este jogo.

    Forca, winrate e numero de partidas existem para qualquer esporte. O resto
    e por genero:

    * GPM/XPM/KDA/duracao sao telemetria por jogador da OpenDota - so Dota 2
      tem. Num FPS "ouro por minuto" nem e conceito do jogo.
    * O saldo de placar (`saldo_placar`) vale para todo jogo com serie
      1-contra-1, mas o substantivo muda: "mapas" num FPS, "jogos" num card
      game, "pontos" no xadrez. `unidade_placar` vem do registro de wikis.

    Cada bloco so entra quando ha dado - nada de linha com travessao.
    """
    # A forca e as features de contexto (quando o modelo aprendeu peso para
    # elas) entram na conta da probabilidade. Winrate e partidas sao leitura.
    features_agora = features_agora or []
    pesos_features = pesos_features or []
    pesa = {
        nome: abs(peso) > 1e-3
        for nome, peso in zip(NOMES_FEATURES, pesos_features)
    }

    fatores = [
        _fator("Força estimada", a.forca, b.forca, "", peso=True, casas=3),
        _fator("Winrate", a.winrate, b.winrate, "%"),
        _fator("Partidas coletadas", a.partidas, b.partidas, "", casas=0),
    ]

    if a.forma_recente is not None or b.forma_recente is not None:
        fatores.append(
            _fator(
                f"Forma (últimos {JANELA_FORMA})",
                a.forma_recente,
                b.forma_recente,
                "%",
                peso=pesa.get("forma_recente", False),
            )
        )

    if unidade_placar and (a.saldo_placar is not None or b.saldo_placar is not None):
        fatores.append(
            _fator(
                f"Saldo de {unidade_placar}", a.saldo_placar, b.saldo_placar, "", casas=2
            )
        )

    telemetria = [
        _fator("Ouro por minuto", a.gpm_medio, b.gpm_medio, "GPM", casas=0),
        _fator("Experiência por minuto", a.xpm_medio, b.xpm_medio, "XPM", casas=0),
        _fator("KDA médio", a.kda_medio, b.kda_medio, "", casas=2),
        _fator(
            "Duração média",
            a.duracao_media_segundos / 60 if a.duracao_media_segundos else None,
            b.duracao_media_segundos / 60 if b.duracao_media_segundos else None,
            "min",
        ),
    ]
    fatores.extend(
        f for f in telemetria if f.valor_a is not None or f.valor_b is not None
    )
    return fatores


def ranking(jogo: str = "dota2", liga: str | None = None) -> list[Equipe]:
    """Equipes ordenadas por forca. E a resposta a 'quem e o favorito'."""
    equipes, _ = estado(jogo)

    if liga:
        with session_scope() as sessao:
            confrontos = _carregar_confrontos(sessao, jogo)
        na_liga = {
            id_e
            for c in confrontos
            if c.liga == liga
            for id_e in (c.id_equipe_a, c.id_equipe_b)
        }
        equipes = {id_e: e for id_e, e in equipes.items() if id_e in na_liga}

    return sorted(equipes.values(), key=lambda e: e.forca, reverse=True)


def ligas(jogo: str = "dota2") -> list[dict[str, Any]]:
    """Campeonatos presentes nos dados, com volume e janela de datas."""
    with session_scope() as sessao:
        confrontos = _carregar_confrontos(sessao, jogo)

    agrupado: dict[str, dict[str, Any]] = {}
    for confronto in confrontos:
        nome = (confronto.liga or "Sem liga").strip()
        entrada = agrupado.setdefault(
            nome,
            {"liga": nome, "confrontos": 0, "equipes": set(), "inicio": None, "fim": None},
        )
        entrada["confrontos"] += 1
        entrada["equipes"].update({confronto.id_equipe_a, confronto.id_equipe_b})
        if confronto.data:
            if entrada["inicio"] is None or confronto.data < entrada["inicio"]:
                entrada["inicio"] = confronto.data
            if entrada["fim"] is None or confronto.data > entrada["fim"]:
                entrada["fim"] = confronto.data

    return sorted(
        (
            {
                "liga": e["liga"],
                "confrontos": e["confrontos"],
                "equipes": len(e["equipes"]),
                "inicio": e["inicio"],
                "fim": e["fim"],
            }
            for e in agrupado.values()
        ),
        key=lambda e: e["confrontos"],
        reverse=True,
    )


# ---------------------------------------------------------------------------
# Agenda
# ---------------------------------------------------------------------------


@dataclass
class ConfrontoAgendado:
    """Um jogo do calendario, com a previsao quando ela e possivel."""

    id_externo: str
    equipe_a_nome: str
    equipe_b_nome: str
    inicio_previsto: datetime
    torneio: str | None
    formato: str | None
    #: `None` quando um dos times nao foi reconciliado ou nao tem historico.
    probabilidade_a: float | None = None
    equipe_a: Equipe | None = None
    equipe_b: Equipe | None = None
    motivo_sem_previsao: str | None = None


def agenda(jogo: str = "dota2", limite: int = 40) -> list[ConfrontoAgendado]:
    """Proximos confrontos do calendario, com a previsao de cada um.

    Partida sem previsao continua na lista. Escondê-la daria a impressao de que
    a agenda e menor do que e, e o motivo ("time sem historico coletado") e
    informacao util - e o que diz onde a coleta precisa crescer.

    **A agenda NAO exige modelo ajustado.** O calendario vem da Liquipedia e a
    previsao vem do nosso ajuste - sao fontes diferentes, e amarrar uma na outra
    fazia um jogo sem modelo (Counter-Strike, Valorant, e outros 70) devolver
    503 no lugar de um calendario que existe e esta completo. Sem forcas, todo
    confronto sai com `probabilidade_a=None` e o motivo diz por que.
    """
    try:
        equipes, relatorio = estado(jogo)
        lado = float(relatorio["vantagem_lado_a"])
        pesos_features = [
            float((relatorio.get("pesos_features") or {}).get(nome, 0.0))
            for nome in NOMES_FEATURES
        ]
        sem_modelo = False
    except FileNotFoundError:
        equipes, lado, pesos_features, sem_modelo = {}, 0.0, [], True

    historico = []
    if not sem_modelo:
        with session_scope() as sessao:
            historico = _carregar_confrontos(sessao, jogo)

    agora = datetime.now(timezone.utc)

    with session_scope() as sessao:
        linhas = sessao.execute(
            select(
                AgendaPartida.id_externo,
                AgendaPartida.equipe_a_nome,
                AgendaPartida.equipe_b_nome,
                AgendaPartida.id_equipe_a,
                AgendaPartida.id_equipe_b,
                AgendaPartida.inicio_previsto,
                AgendaPartida.torneio,
                AgendaPartida.formato,
            )
            .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
            .where(DimJogo.codigo == jogo, AgendaPartida.inicio_previsto >= agora)
            .order_by(AgendaPartida.inicio_previsto)
            .limit(limite)
        ).all()

    confrontos: list[ConfrontoAgendado] = []
    for linha in linhas:
        a = equipes.get(linha[3]) if linha[3] else None
        b = equipes.get(linha[4]) if linha[4] else None

        if sem_modelo:
            # Distinguir dos casos abaixo importa: aqui nao falta o TIME, falta
            # o modelo do jogo inteiro. Dizer "sem historico coletado: Falcons"
            # sobre um time que a Liquipedia conhece bem seria enganoso.
            motivo = (
                f"o modelo de {jogo} não foi ajustado: a previsão precisa de "
                "partidas com resultado, que ainda não são coletadas para este jogo"
            )
            probabilidade = None
        elif a is None or b is None:
            faltando = [
                nome
                for nome, equipe in ((linha[1], a), (linha[2], b))
                if equipe is None
            ]
            motivo = (
                f"sem histórico coletado: {', '.join(faltando)}"
                if faltando
                else None
            )
            probabilidade = None
        else:
            motivo = None
            feats = _features_do_confronto(historico, linha[3], linha[4])
            contexto = sum(p * f for p, f in zip(pesos_features, feats))
            probabilidade = round(
                _probabilidade(a.forca, b.forca, lado, contexto), 4
            )

        confrontos.append(
            ConfrontoAgendado(
                id_externo=linha[0],
                equipe_a_nome=linha[1],
                equipe_b_nome=linha[2],
                inicio_previsto=linha[5],
                torneio=linha[6],
                formato=linha[7],
                probabilidade_a=probabilidade,
                equipe_a=a,
                equipe_b=b,
                motivo_sem_previsao=motivo,
            )
        )

    return confrontos
