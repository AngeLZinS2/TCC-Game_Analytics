"""Testes do cliente MCP do OP.GG e do bloco que o consome.

Nao ha rede aqui. O que se testa e o que decide a corretude: o desempacotamento
da resposta (o servidor responde em dois formatos), a aritmetica das taxas, e -
o mais importante - que uma fonte externa fora do ar vire "um bloco a menos" em
vez de pergunta sem resposta.
"""

from __future__ import annotations

import json

import pytest

from collectors import opgg_mcp
from ml.assistente import _desempenho_externo, _elenco_com_desempenho


class RespostaFalsa:
    def __init__(self, texto: str) -> None:
        self.text = texto


def test_desempacota_json_puro():
    corpo = opgg_mcp._corpo_json(RespostaFalsa('{"jsonrpc":"2.0","result":{"ok":1}}'))
    assert corpo["result"] == {"ok": 1}


def test_desempacota_fluxo_sse():
    """O servidor responde `text/event-stream` em parte das ferramentas.

    Sem tratar as duas formas aqui, cada chamador teria que descobrir sozinho
    qual ferramenta responde em qual formato - e descobriria errando.
    """
    sse = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"parcial":true}}\n'
        "\n"
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":2,"result":{"final":true}}\n'
    )
    corpo = opgg_mcp._corpo_json(RespostaFalsa(sse))
    # A ULTIMA linha de dados e a resposta; pegar a primeira devolveria o
    # estado intermediario como se fosse o resultado.
    assert corpo["result"] == {"final": True}


def test_resposta_ilegivel_vira_indisponivel():
    with pytest.raises(opgg_mcp.OpggIndisponivel):
        opgg_mcp._corpo_json(RespostaFalsa("<html>manutencao</html>"))


def test_taxas_de_agente(monkeypatch):
    """Empate fica fora do denominador da vitoria, e a escolha e sobre o total.

    As duas contas erram de formas diferentes se descuidadas: contar empate
    como derrota rebaixaria todo agente por igual (parece inofensivo, e nao e -
    o numero deixa de bater com o do OP.GG), e dividir a escolha por partidas
    em vez de participacoes daria 10x o valor certo, porque cada partida tem
    dez agentes.
    """
    monkeypatch.setattr(
        opgg_mcp,
        "chamar_ferramenta",
        lambda nome, args: {
            "data": [
                {"characterId": "AAA-BBB", "gameCount": 300, "wins": 150, "defeats": 140, "draws": 10},
                {"characterId": "CCC-DDD", "gameCount": 100, "wins": 40, "defeats": 60},
            ]
        },
    )

    agentes = opgg_mcp.estatisticas_agentes_valorant()

    primeiro, segundo = agentes
    assert primeiro["id_externo"] == "aaa-bbb"  # minusculo, como em dim_personagem
    assert primeiro["winrate"] == round(100 * 150 / 290, 1)
    assert primeiro["pick_rate"] == 75.0  # 300 de 400 participacoes
    assert segundo["winrate"] == 40.0


def test_agente_sem_partida_decidida_e_descartado(monkeypatch):
    """Divisao por zero vira ausencia, nao 500 na API."""
    monkeypatch.setattr(
        opgg_mcp,
        "chamar_ferramenta",
        lambda nome, args: {"data": [{"characterId": "X", "gameCount": 5, "wins": 0, "defeats": 0}]},
    )
    assert opgg_mcp.estatisticas_agentes_valorant() == []


def test_fonte_fora_do_ar_nao_derruba_a_pergunta(monkeypatch):
    """Uma fonte externa indisponivel e um bloco a menos, nao um erro.

    O bloco de elenco volta a ser so o elenco, com a recusa explicita - que e
    exatamente o comportamento de antes do OP.GG existir.
    """
    def explode():
        raise opgg_mcp.OpggIndisponivel("timeout")

    monkeypatch.setattr(opgg_mcp, "estatisticas_agentes_valorant", explode)
    assert _desempenho_externo("valorant") == {}


def test_desempenho_so_para_jogo_coberto():
    """Chamar o OP.GG por causa de Counter-Strike gastaria rede a toa - e o
    servidor so cobre LoL, TFT e Valorant."""
    assert _desempenho_externo("counterstrike") == {}


def test_elenco_ordena_por_escolha_e_marca_a_procedencia():
    """Ordem por taxa de ESCOLHA, nao por vitoria.

    Em Valorant as vitorias ficam entre 48% e 52% (equilibrio de design), entao
    ranquear por elas poria em primeiro um agente pouco jogado por meio ponto.
    E o bloco tem que dizer que o recorte NAO e profissional: "melhor agente no
    meta" quase sempre quer dizer pro play, e responder com soloq seria um
    numero certo respondendo outra pergunta.
    """
    elenco = [
        ("Jett", "Duelista", "aaa"),
        ("Clove", "Controlador", "bbb"),
        ("Vyse", "Sentinela", "ccc"),
    ]
    desempenho = {
        "aaa": {"partidas": 100, "winrate": 50.0, "pick_rate": 4.0},
        "bbb": {"partidas": 300, "winrate": 51.9, "pick_rate": 12.2},
    }

    bloco, serie = _elenco_com_desempenho("VALORANT", elenco, desempenho)

    assert bloco.fonte == "opgg"
    corpo = bloco.conteudo
    assert corpo.index("Clove") < corpo.index("Jett")
    # Sem estatistica nao vira zero: vira ausencia declarada.
    assert "Vyse (Sentinela): sem estatistica no OP.GG" in corpo
    assert "NAO do cenario profissional" in corpo or "nao sao do cenario profissional" in corpo
    assert "meio ponto de diferenca NAO faz um agente 'melhor'" in corpo

    assert serie is not None
    assert [p.rotulo for p in serie.itens] == ["Clove", "Jett"]
    assert serie.unidade == "%"


def test_json_de_ferramenta_nao_json_volta_cru(monkeypatch):
    """Varias ferramentas do OP.GG respondem numa notacao compacta propria.

    Devolver o texto cru e melhor do que estourar: nenhum bloco exibe isso sem
    tratar, e falhar aqui derrubaria tambem as ferramentas que sao JSON.
    """
    class Resp:
        status_code = 200
        text = json.dumps(
            {"jsonrpc": "2.0", "result": {"content": [{"text": "Mid(\"Ahri\",0.51)"}]}}
        )

        def raise_for_status(self):
            return None

    monkeypatch.setattr(opgg_mcp, "_postar", lambda corpo, sessao: Resp())
    monkeypatch.setattr(opgg_mcp, "_sessao", "sessao-de-teste")

    assert opgg_mcp.chamar_ferramenta("lol_list_lane_meta_champions", {}) == 'Mid("Ahri",0.51)'
