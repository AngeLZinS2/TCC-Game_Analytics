"""Testes do parser do HowLongToBeat.

Sem rede: `transformar` sobre RawRecord's montados a partir das fixtures (a
resposta de busca, no formato documentado). O que se protege e o casamento
por similaridade de nome (a parte especifica do HLTB - ele nao tem appid) e a
conversao de segundos para horas.
"""

from __future__ import annotations

from decimal import Decimal

from collectors.base import RawRecord
from etl.transform_hltb import ENDPOINT_BUSCA, FONTE, transformar

APP = 1145360


def _reg(app_id: int, consulta: str, resultado) -> RawRecord:
    return RawRecord(
        fonte=FONTE,
        endpoint=ENDPOINT_BUSCA,
        identificador=str(app_id),
        payload={"app_id": app_id, "consulta": consulta, "resultado": resultado},
    )


def test_casa_o_candidato_mais_parecido(carregar_fixture):
    registros = [_reg(APP, "Hades", carregar_fixture("hltb_search_resultado"))]
    resultado = transformar(registros)

    assert resultado.total == 1
    jogo = resultado.jogos[0]
    assert jogo.app_id == APP
    assert jogo.hltb_id == "62941"
    assert jogo.nome_hltb == "Hades"
    # 84915s / 3600 = 23.5875 -> 23.6
    assert jogo.horas_historia == Decimal("23.6")
    assert jogo.horas_extras == Decimal("48.6")
    assert jogo.horas_completista == Decimal("95.2")


def test_casa_pelo_apelido_quando_o_nome_bate_menos(carregar_fixture):
    """"Hades 2" (nosso catalogo) deve casar com "Hades II" pelo `game_alias`
    ("Hades 2"), nao com "Hades" (o jogo original, nome mais curto)."""
    registros = [_reg(APP, "Hades 2", carregar_fixture("hltb_search_resultado"))]
    resultado = transformar(registros)

    assert resultado.total == 1
    assert resultado.jogos[0].hltb_id == "118218"
    assert resultado.jogos[0].nome_hltb == "Hades II"


def test_tempo_zero_vira_none_nao_zero_horas(carregar_fixture):
    """"Hades' Star" tem `comp_main=0` (ninguem registrou tempo, nao "0h")."""
    registros = [_reg(APP, "Hades Star", carregar_fixture("hltb_search_resultado"))]
    resultado = transformar(registros)

    assert resultado.total == 1
    jogo = resultado.jogos[0]
    assert jogo.hltb_id == "65615"
    assert jogo.horas_historia is None
    assert jogo.horas_extras is None
    assert jogo.horas_completista is None


def test_sem_candidato_bom_o_bastante_marca_sem_hltb(carregar_fixture):
    registros = [_reg(999999, "Um Jogo Que Nao Existe De Verdade", carregar_fixture("hltb_search_sem_resultado"))]
    resultado = transformar(registros)

    assert resultado.total == 0
    assert resultado.sem_hltb == [999999]


def test_nome_completamente_diferente_nao_casa(carregar_fixture):
    """A busca por um termo vago pode devolver candidatos, mas nenhum parecido
    o bastante com o nome original - melhor nao casar do que casar errado."""
    registros = [_reg(APP, "Um Jogo De Corrida Totalmente Diferente", carregar_fixture("hltb_search_resultado"))]
    resultado = transformar(registros)

    assert resultado.total == 0
    assert resultado.sem_hltb == [APP]


def test_ignora_outras_fontes():
    reg = RawRecord(fonte="steam", endpoint="appdetails", identificador="1", payload={})
    assert transformar([reg]).total == 0


def test_ignora_payload_sem_app_id():
    reg = RawRecord(fonte=FONTE, endpoint=ENDPOINT_BUSCA, identificador="1", payload={"resultado": {}})
    assert transformar([reg]).total == 0
