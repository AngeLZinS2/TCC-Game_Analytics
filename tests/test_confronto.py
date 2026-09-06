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
    Equipe,
    _ajustar,
    _fatores_da_previsao,
    _features_do_confronto,
    _features_temporais,
    _forma,
    _h2h,
    _matriz,
    _metricas,
    _probabilidade,
    _saldo_recente,
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


def _placar(a, b, va, pa, pb, minutos=0):
    c = _confronto(a, b, va, minutos)
    return Confronto(**{**c.__dict__, "placar_a": pa, "placar_b": pb})


def test_forma_centrada_em_zero_e_neutra_sem_historico():
    hist = [_confronto(1, 2, True, 0), _confronto(1, 3, True, 1), _confronto(4, 1, True, 2)]
    # time 1: venceu, venceu, perdeu -> 2/3 -> +0.167
    assert _forma(hist, 1) == pytest.approx(2 / 3 - 0.5)
    # time 2: uma partida so -> neutro
    assert _forma(hist, 2) == 0.0
    # time inexistente -> neutro
    assert _forma(hist, 99) == 0.0


def test_h2h_encolhe_para_amostra_pequena():
    # 1 ganhou os dois encontros diretos com 2
    hist = [_confronto(1, 2, True, 0), _confronto(2, 1, False, 1), _confronto(1, 3, True, 2)]
    # (2 + 1) / (2 + 2) - 0.5 = +0.25, nao +0.5
    assert _h2h(hist, 1, 2) == pytest.approx(0.25)
    assert _h2h(hist, 2, 1) == pytest.approx(-0.25)
    # nunca se jogaram -> 0
    assert _h2h(hist, 3, 2) == 0.0


def test_saldo_recente_normaliza_a_margem():
    hist = [_placar(1, 2, True, 3, 0, 0), _placar(3, 1, False, 1, 3, 1)]
    # time 1: venceu 3-0 (margem +1) e venceu 3-1 do lado B (margem +0.5) -> media +0.75
    assert _saldo_recente(hist, 1) == pytest.approx(0.75)
    # Dota (sem placar) -> 0
    assert _saldo_recente([_confronto(1, 2, True)], 1) == 0.0


def test_features_temporais_sao_causais():
    """A feature do confronto i so pode olhar confrontos[:i] - senao a validacao
    walk-forward incluiria o resultado que ela esta prevendo."""
    confrontos = [
        _confronto(1, 2, True, 0),
        _confronto(1, 2, True, 1),
        _confronto(1, 2, True, 2),
    ]
    feats = _features_temporais(confrontos)
    # 1o confronto: nada antes -> tudo 0
    assert feats[0] == [0.0, 0.0, 0.0]
    # 3o confronto: 1 venceu os 2 anteriores -> forma e h2h a favor de 1 (>0)
    assert feats[2][0] > 0  # forma_recente (dif)
    assert feats[2][1] > 0  # confronto_direto


def test_ajustar_trava_feature_negativa_em_zero():
    """A direcao das features e conhecida; coeficiente negativo e ruido -> 0."""
    # Monta um historico onde o time em pior forma vence sempre (sinal invertido):
    # a regressao tentaria um peso negativo para `forma`, e o clip o zera.
    confrontos = []
    for i in range(30):
        # 1 sempre perde as ultimas, mas ganha a proxima - forma anti-correlacionada
        vencedor_a = i % 2 == 0
        confrontos.append(_confronto(1 if vencedor_a else 2, 2 if vencedor_a else 1, True, i))
    feats = _features_temporais(confrontos)
    _, _, _, pesos = _ajustar(confrontos, regularizacao=2.0, features=feats)
    assert all(p >= 0.0 for p in pesos)


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
    forcas, _, _, _ = _ajustar(confrontos, regularizacao=1.0)

    assert forcas[1] > forcas[2] > forcas[4]


def test_regularizacao_forte_encolhe_as_forcas():
    """`C` baixo puxa todo mundo para a media - e o prior de 'nao sabemos'."""
    confrontos = [
        _confronto(1, 2, True, 0),
        _confronto(2, 1, False, 1),
        _confronto(1, 3, True, 2),
        _confronto(3, 2, False, 3),
    ]
    frouxa, _, _, _ = _ajustar(confrontos, regularizacao=10.0)
    apertada, _, _, _ = _ajustar(confrontos, regularizacao=0.01)

    assert max(abs(v) for v in apertada.values()) < max(abs(v) for v in frouxa.values())


def test_uma_classe_so_nao_quebra_o_ajuste():
    """Se o lado A venceu todas, nao ha o que separar - forcas ficam em zero."""
    confrontos = [_confronto(1, 2, True, 0), _confronto(3, 4, True, 1)]
    forcas, lado, peso, _ = _ajustar(confrontos)

    assert set(forcas.values()) == {0.0}
    assert lado == 0.0
    assert peso == 0.0


def test_forcas_cobrem_todas_as_equipes_vistas():
    confrontos = [_confronto(7, 8, True, 0), _confronto(8, 9, False, 1)]
    forcas, _, _, _ = _ajustar(confrontos, regularizacao=1.0)
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


# ---------------------------------------------------------------------------
# Fatores por genero de jogo
# ---------------------------------------------------------------------------


def _equipe(id_equipe: int, **kwargs) -> Equipe:
    return Equipe(id_equipe=id_equipe, nome=f"E{id_equipe}", tag=None, logo_url=None, **kwargs)


def test_fatores_de_fps_nao_trazem_vocabulario_de_moba():
    """CS não tem telemetria por jogador (a Liquipedia dá só o placar). GPM,
    XPM, KDA e duração são conceitos de MOBA e não podem aparecer numa tela de
    FPS - nem como '—'."""
    a = _equipe(1, partidas=4, vitorias=3, forca=1.2)
    b = _equipe(2, partidas=5, vitorias=2, forca=0.4)

    rotulos = [f.rotulo for f in _fatores_da_previsao(a, b)]

    assert "Força estimada" in rotulos and "Winrate" in rotulos
    assert not any(
        termo in r for r in rotulos for termo in ("Ouro", "Experiência", "KDA", "Duração")
    )


def test_saldo_de_placar_usa_o_substantivo_do_genero():
    """"Saldo de mapas" num FPS, "Saldo de jogos" num card game, "Saldo de
    pontos" no xadrez - o mesmo número, o nome que o esporte usa."""
    a = _equipe(1, partidas=6, vitorias=4, forca=0.8, saldo_placar=0.42)
    b = _equipe(2, partidas=5, vitorias=2, forca=0.1, saldo_placar=-0.15)

    fps = [f.rotulo for f in _fatores_da_previsao(a, b, "mapas")]
    cartas = [f.rotulo for f in _fatores_da_previsao(a, b, "jogos")]
    xadrez = [f.rotulo for f in _fatores_da_previsao(a, b, "pontos")]

    assert "Saldo de mapas" in fps
    assert "Saldo de jogos" in cartas
    assert "Saldo de pontos" in xadrez


def test_saldo_nao_aparece_sem_unidade_nem_sem_dado():
    """Battle royale não tem série 1-contra-1 (`unidade_placar` = None); e sem
    saldo nenhum lado, o fator some."""
    com_dado = _equipe(1, partidas=6, vitorias=4, forca=0.8, saldo_placar=0.42)
    sem_dado = _equipe(2, partidas=5, vitorias=2, forca=0.1)

    # unidade None -> nunca
    assert not any(
        f.rotulo.startswith("Saldo")
        for f in _fatores_da_previsao(com_dado, sem_dado, None)
    )
    # unidade ok mas nenhum lado tem saldo -> nao entra
    assert not any(
        f.rotulo.startswith("Saldo")
        for f in _fatores_da_previsao(sem_dado, _equipe(3, partidas=2, forca=0.0), "jogos")
    )


def test_fatores_de_moba_trazem_a_telemetria_quando_ha_dado():
    """Dota tem GPM/XPM/KDA da OpenDota - aí os quatro fatores entram."""
    a = _equipe(1, partidas=10, vitorias=7, forca=0.9, gpm_medio=540.0, xpm_medio=600.0,
                kda_medio=3.1, duracao_media_segundos=2100.0)
    b = _equipe(2, partidas=8, vitorias=3, forca=0.2, gpm_medio=500.0, xpm_medio=560.0,
                kda_medio=2.4, duracao_media_segundos=2400.0)

    rotulos = [f.rotulo for f in _fatores_da_previsao(a, b)]

    assert "Ouro por minuto" in rotulos
    assert "KDA médio" in rotulos
    assert "Duração média" in rotulos


def test_um_lado_com_telemetria_e_o_outro_sem_ainda_mostra_o_fator():
    """Se A jogou no Dota e tem GPM mas B nunca apareceu, o fator entra com o
    lado de B em branco - some só quando NENHUM lado tem o número."""
    a = _equipe(1, partidas=10, vitorias=7, forca=0.9, gpm_medio=540.0)
    b = _equipe(2, partidas=0, vitorias=0, forca=0.0)

    rotulos = [f.rotulo for f in _fatores_da_previsao(a, b)]
    assert "Ouro por minuto" in rotulos


def test_taxa_base_nao_e_arredondada():
    """A taxa base sai em precisao cheia, igual a acuracia.

    Bug real: `taxa_base` ia arredondada em 4 casas e `acuracia` nao, e quem
    decide se "o modelo supera o chute" - a CLI e a tela - compara as duas com
    `>`. O empate virava vitoria ou derrota conforme a quinta casa:

      Call of Duty  11/14 = 0.7857142857 contra base 0.7857  -> "supera"
      Brawl Stars    7/11 = 0.6363636363 contra base 0.6364  -> "nao supera"

    Sao o MESMO caso - modelo que so acerta o lado mais frequente - e um deles
    era anunciado como preditivo com ROC-AUC de 0.182, pior que aleatorio.
    """
    # 11 acertos em 14, todos do lado 1: a acuracia e exatamente a taxa base.
    reais = [1] * 11 + [0] * 3
    probabilidades = [0.9] * 14

    metricas = _metricas(probabilidades, reais)

    assert metricas["acuracia"] == metricas["taxa_base"]
    # E o que o consumidor pergunta: empate NAO supera.
    assert not (metricas["acuracia"] > metricas["taxa_base"])
