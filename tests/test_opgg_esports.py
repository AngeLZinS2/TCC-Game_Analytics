"""Testes da normalizacao de confrontos de LoL vindos do OP.GG.

Sem rede: o que se testa e o `parse`, que e funcao pura. E ai que mora a
corretude desta fonte - um confronto convertido errado vira um placar errado na
tela, e placar errado e pior do que tela vazia.
"""

from __future__ import annotations

from collectors.opgg_esports import (
    OpggEsportsCollector,
    ResultadoOpggEsports,
    _converter,
)
from collectors.base import RawRecord


def _partida(**extra):
    base = {
        "id": 32666,
        "status": "FINISHED",
        "homeScore": 3,
        "awayScore": 1,
        "scheduledAt": "2026-09-04T09:10:00.000Z",
        "numberOfGames": 5,
        "league": "LPL",
        "homeTeam": {"id": "698", "name": "Anyone's Legend", "acronym": "AL"},
        "awayTeam": {"id": "585", "name": "LGD Gaming", "acronym": "LGD"},
    }
    base.update(extra)
    return base


def test_converte_confronto_decidido():
    equipes: dict = {}
    c = _converter(_partida(), equipes)

    assert c is not None
    # O prefixo separa o namespace do OP.GG do `teamid` da Liquipedia: os dois
    # sao inteiros pequenos, e sem ele uma coleta da wiki de LoL fundiria dois
    # times diferentes que por acaso tem o mesmo numero.
    assert c.id_externo == "opgg:32666"
    assert c.equipe_a_externo == "opgg:698"
    assert (c.placar_a, c.placar_b, c.vitoria_a) == (3, 1, True)
    assert c.formato == "Bo5"
    assert c.torneio == "LPL"
    assert len(equipes) == 2


def test_confronto_futuro_nao_ganha_vencedor():
    """`vitoria_a` nulo e o que a tela de Proximos Confrontos filtra por.

    Preencher com `False` faria um jogo que nem comecou aparecer como derrota
    do time da casa - e entraria no ajuste de forcas como resultado real.
    """
    c = _converter(_partida(status="NOT_STARTED", homeScore=0, awayScore=0), {})

    assert c is not None
    assert c.vitoria_a is None
    assert c.placar_a is None and c.placar_b is None


def test_empate_fica_sem_vencedor():
    c = _converter(_partida(homeScore=1, awayScore=1), {})

    assert c is not None
    assert c.vitoria_a is None
    # O placar continua sendo dado: so o vencedor e que nao existe.
    assert (c.placar_a, c.placar_b) == (1, 1)


def test_chaveamento_sem_os_dois_lados_e_descartado():
    """"Vencedor da semifinal 1" ainda nao e confronto.

    Guardar viraria uma linha com time fantasma, que a tela mostraria como se
    fosse uma equipe de verdade.
    """
    assert _converter(_partida(awayTeam=None), {}) is None
    assert _converter(_partida(homeTeam={"id": "1"}), {}) is None


def test_horario_invalido_descarta():
    assert _converter(_partida(scheduledAt=None), {}) is None
    assert _converter(_partida(scheduledAt="ontem"), {}) is None


def test_horario_z_vira_utc():
    c = _converter(_partida(), {})
    assert c is not None
    assert c.inicio_previsto.tzinfo is not None
    assert c.inicio_previsto.utcoffset().total_seconds() == 0


def test_versao_com_resultado_vence_a_duplicada():
    """O mesmo confronto aparece nas duas janelas quando termina entre as
    chamadas. Ficar com a versao sem placar perderia o resultado ate a rodada
    seguinte - e a janela de resultados trava em 50, entao ele poderia sumir de
    vez."""
    coletor = OpggEsportsCollector(raw_storage=None)
    registros = [
        RawRecord(
            fonte="opgg_esports",
            endpoint="x",
            identificador="schedule",
            payload=[_partida(status="NOT_STARTED", homeScore=0, awayScore=0)],
        ),
        RawRecord(
            fonte="opgg_esports",
            endpoint="x",
            identificador="result",
            payload=[_partida()],
        ),
    ]

    resultado = coletor.parse(registros)

    assert len(resultado.confrontos) == 1
    assert resultado.confrontos[0].vitoria_a is True
    assert resultado.total == 1


def test_total_e_o_atributo_que_a_cli_le():
    """`collectors.base._tamanho` procura `total`, nao `__len__`.

    Com `__len__` o resultado nao e uma `Sequence`, cai no ramo final e a CLI
    relatava "processados 1" tendo normalizado 67.
    """
    resultado = ResultadoOpggEsports()
    assert resultado.total == 0
    assert hasattr(resultado, "total")
