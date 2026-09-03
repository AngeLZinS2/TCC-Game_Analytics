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
