"""Testes da bifurcacao de fonte em `ml/confronto.py`: Dota 2 x os demais.

Diferente de `test_confronto.py` (deliberadamente sem banco), este arquivo
precisa de Postgres de pe - as funcoes testadas fazem `JOIN` real contra
`agenda_partida`/`dim_equipe`/`dim_jogo`. Sem banco, o modulo inteiro e
pulado, no mesmo padrao de `test_api.py`.

**Por que invariante e nao contagem exata.** O volume de confrontos de um
jogo que nao e Dota 2 cresce com o tempo (o agendador varre a Liquipedia em
rodizio), entao um teste que exigisse "exatamente N confrontos" quebraria a
cada nova coleta sem que nada estivesse errado. O que se verifica aqui e o
FORMATO da resposta - que a bifurcacao usa a fonte certa e devolve o tipo
certo - tolerando zero dado quando o jogo escolhido para o teste ainda nao
foi coletado nesta maquina.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from db.models import DimJogo
from db.session import get_engine, session_scope
from ml.confronto import (
    _carregar_confrontos,
    _carregar_confrontos_liquipedia,
    _carregar_equipes,
)

#: Um jogo com bastante coleta da Liquipedia (equipes na casa dos milhares) -
#: ver Fase 12. Nao e Dota especificamente PORQUE o ponto aqui e testar o
#: caminho que NAO e a OpenDota.
JOGO_NAO_DOTA = "counterstrike"


@pytest.fixture(scope="module")
def sessao_bd():
    try:
        with get_engine().connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - qualquer falha de conexao serve
        pytest.skip(f"Postgres indisponivel: {type(exc).__name__}")

    with session_scope() as sessao:
        yield sessao


def _jogo_existe(sessao, codigo: str) -> bool:
    return sessao.scalar(select(DimJogo.codigo).where(DimJogo.codigo == codigo)) is not None


def test_carregar_confrontos_bifurca_para_liquipedia_fora_do_dota(sessao_bd):
    """`_carregar_confrontos(jogo != "dota2")` tem que ser a mesma funcao que
    `_carregar_confrontos_liquipedia` chamaria - nao uma copia que pode
    divergir dela com o tempo."""
    if not _jogo_existe(sessao_bd, JOGO_NAO_DOTA):
        pytest.skip(f"{JOGO_NAO_DOTA!r} ainda nao foi semeado em dim_jogo")

    via_router = _carregar_confrontos(sessao_bd, JOGO_NAO_DOTA)
    via_direta = _carregar_confrontos_liquipedia(sessao_bd, JOGO_NAO_DOTA)

    assert [c.id_partida for c in via_router] == [c.id_partida for c in via_direta]


def test_confrontos_de_liquipedia_tem_o_formato_esperado(sessao_bd):
    """Cada `Confronto` de uma fonte Liquipedia obedece o mesmo contrato que
    o Bradley-Terry espera de qualquer fonte: dois lados distintos, um
    vencedor booleano, sem `None` disfarcado."""
    confrontos = _carregar_confrontos(sessao_bd, JOGO_NAO_DOTA)
    if not confrontos:
        pytest.skip(f"nenhum confronto decidido coletado ainda para {JOGO_NAO_DOTA!r}")

    for confronto in confrontos:
        assert confronto.id_equipe_a != confronto.id_equipe_b
        assert isinstance(confronto.vitoria_a, bool)


def test_equipes_fora_do_dota_nao_tem_stats_de_jogador(sessao_bd):
    """A Liquipedia da o placar final, nao telemetria por jogador - GPM/XPM/
    KDA tem que continuar `None`, nunca um numero inventado."""
    if not _jogo_existe(sessao_bd, JOGO_NAO_DOTA):
        pytest.skip(f"{JOGO_NAO_DOTA!r} ainda nao foi semeado em dim_jogo")

    equipes = _carregar_equipes(sessao_bd, JOGO_NAO_DOTA)
    assert equipes, "dim_equipe deveria ter pelo menos uma equipe para este jogo"
    assert all(e.gpm_medio is None for e in equipes.values())
    assert all(e.xpm_medio is None for e in equipes.values())
    assert all(e.kda_medio is None for e in equipes.values())


def test_partidas_da_equipe_conta_os_dois_lados(sessao_bd):
    """Sem esta contagem, `Equipe.partidas` fica em 0 para todo mundo fora do
    Dota e `estado()` descarta a equipe inteira (filtro `if equipe.partidas`),
    mesmo com confrontos de verdade no banco - foi o bug que motivou
    `_preencher_partidas_liquipedia`."""
    confrontos = _carregar_confrontos(sessao_bd, JOGO_NAO_DOTA)
    if not confrontos:
        pytest.skip(f"nenhum confronto decidido coletado ainda para {JOGO_NAO_DOTA!r}")

    equipes = _carregar_equipes(sessao_bd, JOGO_NAO_DOTA)
    algum_id = confrontos[0].id_equipe_a
    assert equipes[algum_id].partidas > 0


def test_dota_continua_pela_openddota_mesmo_com_liquipedia_disponivel(sessao_bd):
    """A bifurcacao e por NOME do jogo, nao por "qual fonte tem mais dado" -
    Dota 2 tem que continuar na OpenDota mesmo que a Liquipedia tambem tenha
    coletado partidas dele."""
    if not _jogo_existe(sessao_bd, "dota2"):
        pytest.skip("dota2 ainda nao foi semeado em dim_jogo")

    confrontos = _carregar_confrontos(sessao_bd, "dota2")
    if not confrontos:
        pytest.skip("nenhum confronto de dota2 coletado ainda")

    # Confronto vindo da OpenDota usa o id de `dim_partida`, que e uma
    # sequencia separada da de `agenda_partida` - nao da para provar "veio da
    # tabela certa" so pelo tipo (os dois sao int), entao o teste que importa
    # de verdade e o regression check acima: `_carregar_confrontos("dota2")`
    # nao pode ser reescrito para chamar `_carregar_confrontos_liquipedia`.
    equipes = _carregar_equipes(sessao_bd, "dota2")
    tem_stats = any(e.gpm_medio is not None for e in equipes.values())
    assert tem_stats, "dota2 deveria ter GPM medio vindo da OpenDota"


def test_torneios_conhecidos_le_da_agenda(sessao_bd):
    """`torneios_conhecidos()` nao e uma lista escrita a mao - ela cresce
    sozinha conforme `agenda_partida.torneio` acumula nomes novos. O teste
    verifica isso contra o banco de verdade: mesma fonte, sem duplicar a
    consulta aqui."""
    from collectors.liquipedia_bracket_collector import torneios_conhecidos

    torneios = torneios_conhecidos(JOGO_NAO_DOTA)
    if not torneios:
        pytest.skip(f"nenhum torneio visto ainda para {JOGO_NAO_DOTA!r}")

    assert all(isinstance(t, str) and t for t in torneios)
    assert len(torneios) == len(set(torneios)), "a lista nao deveria ter repetidos"


def test_torneios_conhecidos_de_jogo_sem_agenda_e_vazia():
    """Um codigo de jogo que nem existe em dim_jogo nao pode levantar - so
    devolve vazio, porque nao ha o que buscar."""
    from collectors.liquipedia_bracket_collector import torneios_conhecidos

    assert torneios_conhecidos("jogo-que-nao-existe-xyz") == []


def test_ratings_externos_sao_z_score_por_snapshot(sessao_bd):
    """`_carregar_ratings_externos` normaliza dentro de cada snapshot: media
    perto de zero, e nenhum valor absurdo. Sem isso o prior entraria numa
    escala arbitraria (a pontuacao da Valve nao significa nada fora da lista
    dela)."""
    from ml.confronto import _carregar_ratings_externos

    snaps = _carregar_ratings_externos(sessao_bd, "counterstrike")
    if not snaps:
        pytest.skip("ranking da Valve nao coletado nesta maquina")

    import statistics

    for _data, ratings in snaps:
        if len(ratings) < 2:
            continue
        media = statistics.fmean(ratings.values())
        assert abs(media) < 1e-6
        assert all(abs(v) < 6 for v in ratings.values())


def test_ratings_em_e_point_in_time(sessao_bd):
    """`_ratings_em` devolve o snapshot vigente na data pedida, nunca um
    posterior - e o que impede o ranking de agosto de vazar na previsao de
    julho na validacao walk-forward."""
    from datetime import date, timedelta

    from ml.confronto import _carregar_ratings_externos, _ratings_em

    snaps = _carregar_ratings_externos(sessao_bd, "counterstrike")
    if len(snaps) < 2:
        pytest.skip("menos de dois snapshots do ranking - rode collect --todos")

    (_data0, r0), (data1, _r1) = snaps[0], snaps[1]
    # Um dia antes do segundo snapshot ainda enxerga o primeiro.
    assert _ratings_em(snaps, data1 - timedelta(days=1)) == r0
    # Antes de tudo: dicionario vazio, nao erro.
    assert _ratings_em(snaps, date(2000, 1, 1)) == {}
    # Sem data (modelo final): o mais recente.
    assert _ratings_em(snaps, None) == snaps[-1][1]


def test_jogo_sem_ranking_nao_tem_prior(sessao_bd):
    """Todo jogo que nao e CS: `_carregar_ratings_externos` vazio, e ai o
    modulo volta a ser o Bradley-Terry puro da Fase 14 - sem coluna a mais."""
    from ml.confronto import _carregar_ratings_externos

    assert _carregar_ratings_externos(sessao_bd, "dota2") == []
    assert _carregar_ratings_externos(sessao_bd, "valorant") == []


def test_partida_decidida_fora_do_dota_nunca_fica_sem_equipe(sessao_bd):
    """O bug que o usuario apontou: jogos com confronto ja 100% decidido e o
    sistema "nao consegue trazer". A causa era FK nula - o time da agenda nao
    estava em `dim_equipe` porque o coletor de paginas ainda nao passou naquela
    wiki. `load_liquipedia._garantir_equipes` fecha isso: fora do Dota 2, o
    nome da agenda vira equipe. Entao toda partida DECIDIDA de um jogo que nao
    e Dota tem que ter as duas FKs - senao ela some do Bradley-Terry."""
    linhas = sessao_bd.execute(
        text(
            """
            SELECT j.codigo,
                   COUNT(*) FILTER (
                       WHERE a.id_equipe_a IS NULL OR a.id_equipe_b IS NULL
                   ) AS sem_fk
            FROM agenda_partida a
            JOIN dim_jogo j ON j.id_jogo = a.id_jogo
            WHERE a.vitoria_a IS NOT NULL AND j.codigo <> 'dota2'
            GROUP BY j.codigo
            """
        )
    ).all()
    if not linhas:
        pytest.skip("nenhuma partida decidida fora do Dota coletada nesta maquina")

    orfas = {codigo: sem_fk for codigo, sem_fk in linhas if sem_fk}
    assert not orfas, f"partidas decididas sem equipe resolvida: {orfas}"
