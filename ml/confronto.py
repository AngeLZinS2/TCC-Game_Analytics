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
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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


@dataclass(frozen=True)
class Confronto:
    id_partida: int
    data: datetime | None
    id_equipe_a: int
    id_equipe_b: int
    vitoria_a: bool
    liga: str | None


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
    #: Quanto este fator explica da probabilidade. So a forca tem peso direto;
    #: os demais sao contexto que ajuda a ler o resultado.
    peso_no_modelo: bool


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

    if jogo != "dota2":
        _preencher_partidas_liquipedia(sessao, jogo, equipes)
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


def _matriz(confrontos: list[Confronto], indices: dict[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Matriz de indicadores: +1 para o time do lado A, -1 para o do lado B.

    E a forma padrao de escrever Bradley-Terry como regressao logistica. Cada
    coluna e um time, e o coeficiente aprendido para ela e a forca dele.
    """
    X = np.zeros((len(confrontos), len(indices)))
    y = np.zeros(len(confrontos), dtype=int)

    for linha, confronto in enumerate(confrontos):
        X[linha, indices[confronto.id_equipe_a]] = 1.0
        X[linha, indices[confronto.id_equipe_b]] = -1.0
        y[linha] = 1 if confronto.vitoria_a else 0

    return X, y


def _escolher_regularizacao(confrontos: list[Confronto]) -> float:
    """Escolhe `C` por validacao cruzada DENTRO da janela recebida.

    Recebe so o treino. Rodar isto sobre o conjunto inteiro e depois reportar a
    metrica de teste daria um numero otimista: o valor de `C` ja teria visto as
    partidas que ele e julgado a prever.
    """
    ids = sorted({c.id_equipe_a for c in confrontos} | {c.id_equipe_b for c in confrontos})
    indices = {id_equipe: posicao for posicao, id_equipe in enumerate(ids)}
    X, y = _matriz(confrontos, indices)

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
            perdas.append(
                log_loss(
                    y[validacao],
                    modelo.predict_proba(X[validacao])[:, 1],
                    labels=[0, 1],
                )
            )

        if perdas and float(np.mean(perdas)) < melhor_perda:
            melhor_perda, melhor_c = float(np.mean(perdas)), candidato

    return melhor_c


def _ajustar(
    confrontos: list[Confronto], regularizacao: float | None = None
) -> tuple[dict[int, float], float]:
    """Devolve a forca de cada equipe e a vantagem do lado A (em log-odds)."""
    ids = sorted({c.id_equipe_a for c in confrontos} | {c.id_equipe_b for c in confrontos})
    indices = {id_equipe: posicao for posicao, id_equipe in enumerate(ids)}

    X, y = _matriz(confrontos, indices)

    # Uma classe so (todo mundo ganhou de um lado) nao tem o que ajustar.
    if len(set(y)) < 2:
        return {id_equipe: 0.0 for id_equipe in ids}, 0.0

    modelo = LogisticRegression(
        C=regularizacao if regularizacao is not None else _escolher_regularizacao(confrontos),
        max_iter=2000,
        random_state=SEMENTE,
    )
    modelo.fit(X, y)

    forcas = {
        id_equipe: float(modelo.coef_[0][posicao]) for id_equipe, posicao in indices.items()
    }
    return forcas, float(modelo.intercept_[0])


def _probabilidade(forca_a: float, forca_b: float, lado: float) -> float:
    return float(1.0 / (1.0 + np.exp(-((forca_a - forca_b) + lado))))


def _avaliar_walk_forward(confrontos: list[Confronto]) -> dict[str, Any]:
    """Reajusta as forcas antes de cada partida do periodo de teste.

    O corte e temporal: nenhuma partida do teste influencia a forca com que ela
    propria e prevista. E mais caro que um split unico - reajusta o modelo a
    cada partida - mas com 71 confrontos isso custa milissegundos, e e a unica
    forma de o numero significar alguma coisa.
    """
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

        # `C` sai da validacao cruzada dentro do historico, nunca do teste.
        forcas, lado = _ajustar(historico, _escolher_regularizacao(historico))
        probabilidades.append(
            _probabilidade(
                forcas.get(alvo.id_equipe_a, 0.0), forcas.get(alvo.id_equipe_b, 0.0), lado
            )
        )
        reais.append(1 if alvo.vitoria_a else 0)
        avaliadas.append(alvo.id_partida)

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
        "taxa_base": round(taxa_base, 4),
        # Com poucas dezenas de partidas, o intervalo importa mais que o ponto.
        # E o erro padrao binomial da propria acuracia.
        "margem_erro": round(
            1.96
            * float(np.sqrt(accuracy_score(reais, previsto) * (1 - accuracy_score(reais, previsto)) / len(reais))),
            4,
        ),
    }


def ajustar_e_salvar(jogo: str = "dota2") -> dict[str, Any]:
    """Ajusta as forcas sobre todo o historico e grava o relatorio."""
    with session_scope() as sessao:
        confrontos = _carregar_confrontos(sessao, jogo)
        equipes = _carregar_equipes(sessao, jogo)

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

    regularizacao = _escolher_regularizacao(confrontos)
    forcas, lado = _ajustar(confrontos, regularizacao)

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

    validacao = _avaliar_walk_forward(confrontos)

    PASTA.mkdir(parents=True, exist_ok=True)
    relatorio = {
        "ajustado_em": datetime.now(timezone.utc).isoformat(),
        "jogo": jogo,
        "metodo": "Bradley-Terry regularizado (regressão logística sobre indicadores)",
        "regularizacao_C": regularizacao,
        "grade_regularizacao": list(GRADE_REGULARIZACAO),
        "confrontos": len(confrontos),
        "equipes": len(forcas),
        "vantagem_lado_a": round(lado, 4),
        "probabilidade_lado_a_entre_iguais": round(_probabilidade(0.0, 0.0, lado), 4),
        "primeira_partida": confrontos[0].data.isoformat() if confrontos[0].data else None,
        "ultima_partida": confrontos[-1].data.isoformat() if confrontos[-1].data else None,
        "validacao": validacao,
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

    probabilidade = _probabilidade(a.forca, b.forca, lado)

    with session_scope() as sessao:
        confrontos = _carregar_confrontos(sessao, jogo)

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

    return Previsao(
        equipe_a=a,
        equipe_b=b,
        probabilidade_a=round(probabilidade, 4),
        probabilidade_b=round(1 - probabilidade, 4),
        contribuicao_forca=round(a.forca - b.forca, 4),
        contribuicao_lado=round(lado, 4),
        confrontos_diretos=len(diretos),
        vitorias_diretas_a=vitorias_diretas_a,
        fatores=[
            # A forca e o unico fator que entra na conta da probabilidade. Os
            # outros sao o contexto que explica de onde ela veio - marca-los
            # como se pesassem seria mentir sobre o modelo.
            _fator("Força no ranking", a.forca, b.forca, "", peso=True, casas=3),
            _fator("Winrate", a.winrate, b.winrate, "%"),
            _fator("Partidas coletadas", a.partidas, b.partidas, "", casas=0),
            _fator("Ouro por minuto", a.gpm_medio, b.gpm_medio, "GPM", casas=0),
            _fator("Experiência por minuto", a.xpm_medio, b.xpm_medio, "XPM", casas=0),
            _fator("KDA médio", a.kda_medio, b.kda_medio, "", casas=2),
            _fator(
                "Duração média",
                a.duracao_media_segundos / 60 if a.duracao_media_segundos else None,
                b.duracao_media_segundos / 60 if b.duracao_media_segundos else None,
                "min",
            ),
        ],
    )


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
        sem_modelo = False
    except FileNotFoundError:
        equipes, lado, sem_modelo = {}, 0.0, True

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
            probabilidade = round(_probabilidade(a.forca, b.forca, lado), 4)

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
