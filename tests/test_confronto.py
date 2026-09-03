"""Testes do nucleo do Bradley-Terry.

Sao as partes deterministas e sem banco: a montagem da matriz de indicadores, a
funcao de probabilidade e o comportamento da regularizacao. E onde um erro
passaria despercebido - trocar o sinal de um lado na matriz nao levanta
excecao nenhuma, so inverte todas as previsoes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from ml.confronto import (
    Confronto,
    _ajustar,
    _matriz,
    _probabilidade,
    arquivo_metricas,
    carregar_relatorio,
)


def _confronto(a: int, b: int, vitoria_a: bool, minutos: int = 0) -> Confronto:
    return Confronto(
        id_partida=a * 1000 + b,
        data=datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(minutes=minutos),
        id_equipe_a=a,
        id_equipe_b=b,
        vitoria_a=vitoria_a,
        liga="Teste",
    )


def test_matriz_marca_lado_a_positivo_e_lado_b_negativo():
    """O sinal e o contrato: invertê-lo inverteria todas as previsões."""
    confrontos = [_confronto(1, 2, True), _confronto(2, 3, False)]
    indices = {1: 0, 2: 1, 3: 2}

    X, y = _matriz(confrontos, indices)

    assert X[0].tolist() == [1.0, -1.0, 0.0]
    assert X[1].tolist() == [0.0, 1.0, -1.0]
    assert y.tolist() == [1, 0]


def test_matriz_zera_equipes_ausentes_da_partida():
    X, _ = _matriz([_confronto(1, 3, True)], {1: 0, 2: 1, 3: 2})
    assert X[0][1] == 0.0


def test_probabilidade_e_simetrica_em_torno_de_50():
    assert _probabilidade(0.0, 0.0, 0.0) == pytest.approx(0.5)
    acima = _probabilidade(1.0, 0.0, 0.0)
    abaixo = _probabilidade(0.0, 1.0, 0.0)
    assert acima + abaixo == pytest.approx(1.0)
    assert acima > 0.5 > abaixo


def test_vantagem_de_lado_desloca_a_probabilidade():
    """O intercepto e a vantagem do lado, separada da qualidade do time."""
    sem_vantagem = _probabilidade(0.0, 0.0, 0.0)
    com_vantagem = _probabilidade(0.0, 0.0, 0.5)
    assert com_vantagem > sem_vantagem


def test_time_que_so_vence_recebe_forca_maior():
    """1 vence todo mundo, 4 perde de todo mundo, 2 e 3 ficam no meio.

    Os lados sao alternados de proposito: com todos os vencedores no lado A o
    rotulo teria uma classe so, e o ajuste devolveria zeros - o teste passaria
    a medir o curto-circuito em vez do modelo.
    """
    confrontos = [
        _confronto(1, 2, True, 0),   # 1 vence
        _confronto(3, 1, False, 1),  # 1 vence, jogando do lado B
        _confronto(1, 4, True, 2),   # 1 vence
        _confronto(4, 2, False, 3),  # 2 vence
        _confronto(4, 3, False, 4),  # 3 vence
        _confronto(2, 3, True, 5),   # 2 vence
    ]
    forcas, _ = _ajustar(confrontos, regularizacao=1.0)

    assert forcas[1] > forcas[2] > forcas[4]


def test_regularizacao_forte_encolhe_as_forcas():
    """`C` baixo puxa todo mundo para a media - e o prior de 'nao sabemos'."""
    confrontos = [
        _confronto(1, 2, True, 0),
        _confronto(2, 1, False, 1),
        _confronto(1, 3, True, 2),
        _confronto(3, 2, False, 3),
    ]
    frouxa, _ = _ajustar(confrontos, regularizacao=10.0)
    apertada, _ = _ajustar(confrontos, regularizacao=0.01)

    assert max(abs(v) for v in apertada.values()) < max(abs(v) for v in frouxa.values())


def test_uma_classe_so_nao_quebra_o_ajuste():
    """Se o lado A venceu todas, nao ha o que separar - forcas ficam em zero."""
    confrontos = [_confronto(1, 2, True, 0), _confronto(3, 4, True, 1)]
    forcas, lado = _ajustar(confrontos)

    assert set(forcas.values()) == {0.0}
    assert lado == 0.0


def test_forcas_cobrem_todas_as_equipes_vistas():
    confrontos = [_confronto(7, 8, True, 0), _confronto(8, 9, False, 1)]
    forcas, _ = _ajustar(confrontos, regularizacao=1.0)
    assert set(forcas) == {7, 8, 9}
    assert all(np.isfinite(valor) for valor in forcas.values())


# ---------------------------------------------------------------------------
# O artefato por jogo
# ---------------------------------------------------------------------------


def test_cada_jogo_tem_seu_arquivo_de_metricas():
    """Era UM arquivo para todos os jogos, e isso era um bug silencioso.

    `carregar_relatorio()` lia `metricas_confronto.json` sem olhar de qual jogo
    ele era, entao `/api/ml/confronto/relatorio?jogo=counterstrike` devolvia o
    relatorio do Dota 2 - com `"jogo": "dota2"` dentro da propria resposta.
    Numero certo respondendo a pergunta errada.
    """
    de_dota = arquivo_metricas("dota2")
    de_cs = arquivo_metricas("counterstrike")

    assert de_dota != de_cs
    assert "dota2" in de_dota.name
    assert "counterstrike" in de_cs.name


def test_jogo_nunca_ajustado_devolve_none():
    """`None` e nao o relatorio de outro jogo - a diferenca e o bug acima."""
    assert carregar_relatorio("jogo-que-nao-existe-xyz") is None
