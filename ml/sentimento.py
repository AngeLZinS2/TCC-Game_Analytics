"""Classificador de sentimento sobre o texto das avaliacoes da Steam.

O rotulo nao foi anotado a mao: e o `voted_up` da propria avaliacao, o polegar
que o autor deu. Isso muda a natureza do problema - nao ha juiz humano no meio,
e o que o modelo aprende e a relacao entre o texto que a pessoa escreveu e o
voto que ela mesma deu.

Duas diferencas em relacao ao modelo de previsao de partida:

* **O split e estratificado, nao agrupado.** La, minutos da mesma partida eram
  quase o mesmo ponto e precisavam ficar do mesmo lado. Aqui a unidade e uma
  avaliacao escrita por uma pessoa, independente das outras.
* **A classe e desbalanceada** (perto de 80% positivas). Acuracia sozinha
  enganaria: prever "positivo" sempre ja acerta 80%. Por isso o relatorio traz
  ROC-AUC, F1 e acuracia balanceada, e os modelos usam `class_weight`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
from sklearn.base import BaseEstimator
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sqlalchemy import func, select

from db.models import DimJogoSteam, FatoAvaliacaoSteam
from db.session import session_scope
from ml.modelos import SEMENTE

logger = logging.getLogger(__name__)

PASTA = Path(__file__).resolve().parent.parent / "data" / "modelos"
ARQUIVO_METRICAS = PASTA / "metricas_sentimento.json"

FRACAO_TESTE = 0.25

#: Minimo de caracteres para uma avaliacao entrar no treino. Abaixo disso o
#: texto e quase sempre uma palavra solta ("bom", "lixo") - o modelo acerta por
#: memorizacao de token, nao por leitura, e a metrica sobe sem significar nada.
MINIMO_CARACTERES = 20


@dataclass(frozen=True)
class DefinicaoSentimento:
    chave: str
    nome: str
    familia: str
    descricao: str
    construir: Callable[[], BaseEstimator]


CATALOGO: tuple[DefinicaoSentimento, ...] = (
    DefinicaoSentimento(
        chave="tfidf_logistica",
        nome="TF-IDF + Regressão Logística",
        familia="Linear sobre palavras",
        descricao=(
            "Vetoriza por palavra e bigrama, depois classifica linearmente. "
            "É o único dos três cujos pesos se leem diretamente como "
            "'palavras que puxam para positivo ou negativo'."
        ),
        construir=lambda: Pipeline(
            [
                (
                    "vetor",
                    TfidfVectorizer(
                        ngram_range=(1, 2),
                        min_df=2,
                        sublinear_tf=True,
                        strip_accents="unicode",
                    ),
                ),
                (
                    "modelo",
                    LogisticRegression(
                        max_iter=2000,
                        # A classe positiva domina; sem reponderar, o modelo
                        # aprende a chutar "positivo" e para de olhar o texto.
                        class_weight="balanced",
                        random_state=SEMENTE,
                    ),
                ),
            ]
        ),
    ),
    DefinicaoSentimento(
        chave="tfidf_svm",
        nome="TF-IDF de caracteres + SVM",
        familia="Margem sobre n-gramas de caractere",
        descricao=(
            "Vetoriza por sequências de 3 a 5 caracteres dentro das palavras. "
            "Aguenta erro de digitação, gíria e mistura de idiomas, que é "
            "exatamente o que uma avaliação da Steam tem."
        ),
        construir=lambda: Pipeline(
            [
                (
                    "vetor",
                    TfidfVectorizer(
                        analyzer="char_wb",
                        ngram_range=(3, 5),
                        min_df=2,
                        sublinear_tf=True,
                    ),
                ),
                (
                    "modelo",
                    # LinearSVC nao devolve probabilidade; a calibracao por
                    # sigmoide sobre validacao cruzada da uma, e sem ela o
                    # log-loss nao existiria para comparar com os outros dois.
                    CalibratedClassifierCV(
                        LinearSVC(class_weight="balanced", random_state=SEMENTE),
                        method="sigmoid",
                        cv=3,
                    ),
                ),
            ]
        ),
    ),
    DefinicaoSentimento(
        chave="tfidf_naive_bayes",
        nome="TF-IDF + Complement Naive Bayes",
        familia="Probabilístico",
        descricao=(
            "Variante do Naive Bayes feita para classes desbalanceadas. "
            "Treina em milissegundos e serve de piso: se os outros dois não o "
            "batem, a complexidade não se pagou."
        ),
        construir=lambda: Pipeline(
            [
                (
                    "vetor",
                    TfidfVectorizer(
                        ngram_range=(1, 2),
                        min_df=2,
                        sublinear_tf=True,
                        strip_accents="unicode",
                    ),
                ),
                ("modelo", ComplementNB()),
            ]
        ),
    ),
)


@dataclass
class Conjunto:
    textos: list[str]
    rotulos: np.ndarray
    idioma: str
    #: Quantas avaliacoes existem no banco antes de qualquer filtro.
    total_no_banco: int
    descartadas_curtas: int


def idioma_dominante() -> tuple[str, int]:
    """O idioma com mais avaliacoes coletadas, e quantas.

    Treinar sobre a mistura de idiomas produziria um vocabulario em que
    "хорошая" e "good" sao tokens sem relacao, e o modelo aprenderia a detectar
    o idioma junto com o sentimento. Um idioma so mantem a pergunta limpa.
    """
    with session_scope() as sessao:
        linha = sessao.execute(
            select(FatoAvaliacaoSteam.idioma, func.count().label("n"))
            .where(FatoAvaliacaoSteam.idioma.is_not(None))
            .group_by(FatoAvaliacaoSteam.idioma)
            .order_by(func.count().desc())
            .limit(1)
        ).first()

    if linha is None:
        raise ValueError(
            "nenhuma avaliacao com idioma no banco. "
            "Rode `cli.py collect steam` antes de treinar."
        )
    return linha[0], linha[1]


def carregar(idioma: str | None = None) -> Conjunto:
    """Le `fato_avaliacao_steam` e devolve textos e rotulos."""
    escolhido = idioma or idioma_dominante()[0]

    with session_scope() as sessao:
        total = sessao.scalar(select(func.count()).select_from(FatoAvaliacaoSteam)) or 0

        linhas = sessao.execute(
            select(FatoAvaliacaoSteam.texto, FatoAvaliacaoSteam.recomendado)
            .where(FatoAvaliacaoSteam.idioma == escolhido)
            .order_by(FatoAvaliacaoSteam.id)
        ).all()

    curtas = sum(1 for texto, _ in linhas if len(texto) < MINIMO_CARACTERES)
    uteis = [(texto, rotulo) for texto, rotulo in linhas if len(texto) >= MINIMO_CARACTERES]

    return Conjunto(
        textos=[texto for texto, _ in uteis],
        rotulos=np.array([1 if rotulo else 0 for _, rotulo in uteis], dtype=int),
        idioma=escolhido,
        total_no_banco=total,
        descartadas_curtas=curtas,
    )


def _termos_influentes(modelo: Any, quantidade: int = 12) -> dict[str, list[list[Any]]]:
    """As palavras de maior peso para cada lado, quando o modelo permite ler.

    So a regressao logistica sobre palavras da isso de forma honesta. O SVM de
    caracteres tem peso por fragmento ("bug", "uga") - fatiar palavra ali daria
    uma lista bonita e sem sentido - e o Naive Bayes tem log-probabilidade, que
    nao e comparavel. Nesses casos devolve vazio, e a tela nao mostra o painel.
    """
    vetor = modelo.named_steps.get("vetor")
    estimador = modelo.named_steps.get("modelo")

    coeficientes = getattr(estimador, "coef_", None)
    if vetor is None or coeficientes is None or vetor.analyzer != "word":
        return {"positivos": [], "negativos": []}

    nomes = vetor.get_feature_names_out()
    pesos = coeficientes[0]
    ordem = np.argsort(pesos)

    return {
        "negativos": [
            [nomes[i], round(float(pesos[i]), 4)] for i in ordem[:quantidade]
        ],
        "positivos": [
            [nomes[i], round(float(pesos[i]), 4)] for i in ordem[-quantidade:][::-1]
        ],
    }


def treinar(idioma: str | None = None) -> dict[str, Any]:
    """Treina o catalogo de sentimento e grava artefatos + metricas."""
    conjunto = carregar(idioma)

    if len(conjunto.textos) < 60 or len(set(conjunto.rotulos)) < 2:
        raise ValueError(
            f"avaliacoes de menos em {conjunto.idioma!r} para treinar "
            f"({len(conjunto.textos)} com as duas classes). "
            "Colete mais com `cli.py collect steam`."
        )

    separador = StratifiedShuffleSplit(
        n_splits=1, test_size=FRACAO_TESTE, random_state=SEMENTE
    )
    indices_treino, indices_teste = next(
        separador.split(conjunto.textos, conjunto.rotulos)
    )

    textos = np.array(conjunto.textos, dtype=object)
    X_treino, X_teste = textos[indices_treino], textos[indices_teste]
    y_treino, y_teste = conjunto.rotulos[indices_treino], conjunto.rotulos[indices_teste]

    PASTA.mkdir(parents=True, exist_ok=True)
    resultados: list[dict[str, Any]] = []

    for definicao in CATALOGO:
        modelo = definicao.construir()

        inicio = datetime.now(timezone.utc)
        modelo.fit(list(X_treino), y_treino)
        segundos = (datetime.now(timezone.utc) - inicio).total_seconds()

        previsto = modelo.predict(list(X_teste))
        probabilidade = modelo.predict_proba(list(X_teste))[:, 1]

        joblib.dump(modelo, PASTA / f"sentimento_{definicao.chave}.joblib")

        resultados.append(
            {
                "chave": definicao.chave,
                "nome": definicao.nome,
                "familia": definicao.familia,
                "descricao": definicao.descricao,
                "acuracia": float(accuracy_score(y_teste, previsto)),
                # Media da revocacao das duas classes. Com 80% de positivas, e
                # ela que denuncia o modelo que so aprendeu a classe maior.
                "acuracia_balanceada": float(balanced_accuracy_score(y_teste, previsto)),
                "precisao": float(precision_score(y_teste, previsto, zero_division=0)),
                "revocacao": float(recall_score(y_teste, previsto, zero_division=0)),
                "f1": float(f1_score(y_teste, previsto, zero_division=0)),
                "f1_negativa": float(
                    f1_score(y_teste, previsto, pos_label=0, zero_division=0)
                ),
                "roc_auc": float(roc_auc_score(y_teste, probabilidade)),
                "log_loss": float(log_loss(y_teste, probabilidade, labels=[0, 1])),
                "matriz_confusao": confusion_matrix(
                    y_teste, previsto, labels=[0, 1]
                ).tolist(),
                "segundos_treino": round(segundos, 3),
                "termos": _termos_influentes(modelo),
            }
        )
        logger.info(
            "modelo de sentimento treinado",
            extra={"modelo": definicao.chave, "roc_auc": round(resultados[-1]["roc_auc"], 4)},
        )

    # Escolhido por ROC-AUC, nao por acuracia: com 80% de uma classe so, a
    # acuracia premia quem ignora a minoritaria, e a tela precisa justamente
    # separar as duas.
    ativo = max(resultados, key=lambda r: r["roc_auc"])

    with session_scope() as sessao:
        jogos = sessao.scalar(
            select(func.count(func.distinct(FatoAvaliacaoSteam.app_id)))
            .select_from(FatoAvaliacaoSteam)
            .join(DimJogoSteam, DimJogoSteam.app_id == FatoAvaliacaoSteam.app_id)
        )

    relatorio = {
        "treinado_em": datetime.now(timezone.utc).isoformat(),
        "idioma": conjunto.idioma,
        "modelo_ativo": ativo["chave"],
        "conjunto": {
            "avaliacoes": len(conjunto.textos),
            "total_no_banco": conjunto.total_no_banco,
            "descartadas_curtas": conjunto.descartadas_curtas,
            "minimo_caracteres": MINIMO_CARACTERES,
            "jogos": int(jogos or 0),
            "treino": int(len(indices_treino)),
            "teste": int(len(indices_teste)),
            "taxa_base": round(float(conjunto.rotulos.mean()), 4),
            "fracao_teste": FRACAO_TESTE,
            "estratificacao": "rotulo",
        },
        "modelos": resultados,
    }

    ARQUIVO_METRICAS.write_text(
        json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return relatorio


def carregar_metricas() -> dict[str, Any] | None:
    if not ARQUIVO_METRICAS.exists():
        return None
    return json.loads(ARQUIVO_METRICAS.read_text(encoding="utf-8"))


def carregar_modelo(chave: str) -> Any:
    caminho = PASTA / f"sentimento_{chave}.joblib"
    if not caminho.exists():
        raise FileNotFoundError(
            f"modelo de sentimento {chave!r} nao treinado. "
            "Rode `cli.py train-sentimento` primeiro."
        )
    return joblib.load(caminho)


# ---------------------------------------------------------------------------
# Aspectos
# ---------------------------------------------------------------------------

#: Termos que marcam do que a avaliacao esta falando.
#:
#: Isto NAO e um modelo: e uma lista de palavras. A tela mostra "entre as
#: avaliacoes que mencionam X, quantas recomendam" - uma contagem sobre o
#: rotulo verdadeiro, nao uma previsao. Chamar isso de "analise de sentimento
#: por aspecto" seria vender um modelo que nao existe; o que existe e um recorte
#: transparente, e a tela diz exatamente isso.
#:
#: Os termos sao em ingles porque o corpus treinado e em ingles. Um lexico por
#: idioma seria o proximo passo, nao uma traducao destes.
ASPECTOS: dict[str, tuple[str, ...]] = {
    "Jogabilidade": ("gameplay", "mechanic", "control", "combat", "movement"),
    "Desempenho": ("fps", "lag", "crash", "stutter", "optimi", "performance", "bug"),
    "Balanceamento": ("balance", "nerf", "buff", "broken", "overpowered", "meta"),
    "Comunidade": ("community", "toxic", "player base", "teammate", "matchmaking"),
    "Monetização": ("price", "expensive", "microtransaction", "dlc", "battle pass",
                    "pay to win", "p2w", "worth"),
    "Conteúdo": ("content", "update", "patch", "story", "map", "grind", "endgame"),
    "Anticheat": ("cheat", "hacker", "aimbot", "anti-cheat", "vac", "smurf"),
}
