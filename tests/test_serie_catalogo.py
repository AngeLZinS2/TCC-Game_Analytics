"""A regra que decide onde a serie agregada do catalogo termina.

A coleta percorre o catalogo ao longo de uma janela inteira. Quando ela e
interrompida no meio, a janela fica com uma fracao dos jogos - e somar essa
fracao ao lado de uma janela completa compara populacoes diferentes. Medido em
2026-09-15: 154 jogos numa janela, 10 na seguinte, e o KPI anunciava "-100%"
com o sparkline despencando ate o chao sem que jogador nenhum tivesse saido.
"""

from datetime import datetime, timedelta, timezone

from controllers.routers.steam import _sem_janela_incompleta
from views.schemas import PontoSerieTotal

BASE = datetime(2026, 9, 15, tzinfo=timezone.utc)


def ponto(hora: int, jogadores: int, jogos: int) -> PontoSerieTotal:
    return PontoSerieTotal(
        janela_coleta=BASE + timedelta(hours=hora),
        jogadores_simultaneos=jogadores,
        jogos=jogos,
    )


def test_corta_janela_final_com_coleta_pela_metade():
    serie = [
        ponto(0, 4_500_000, 150),
        ponto(1, 4_400_000, 154),
        ponto(2, 6, 10),  # coleta interrompida
    ]
    assert [p.jogos for p in _sem_janela_incompleta(serie)] == [150, 154]


def test_corta_mais_de_uma_janela_incompleta_no_fim():
    serie = [ponto(0, 4_500_000, 150), ponto(1, 900, 20), ponto(2, 6, 10)]
    assert [p.jogos for p in _sem_janela_incompleta(serie)] == [150]


def test_mantem_buraco_no_meio_da_serie():
    """Uma janela rala NO MEIO e historico de verdade - a coleta ficou fora do
    ar naquele dia, e esconder isso reescreveria o passado."""
    serie = [ponto(0, 4_500_000, 150), ponto(1, 900, 10), ponto(2, 4_400_000, 154)]
    assert [p.jogos for p in _sem_janela_incompleta(serie)] == [150, 10, 154]


def test_serie_inteira_rala_volta_como_veio():
    """Catalogo recem-criado: todas as janelas tem poucos jogos porque so ha
    poucos jogos. Cortar tudo deixaria a tela vazia sem motivo."""
    serie = [ponto(0, 100, 3), ponto(1, 120, 3)]
    assert len(_sem_janela_incompleta(serie)) == 2


def test_serie_vazia_nao_quebra():
    assert _sem_janela_incompleta([]) == []
