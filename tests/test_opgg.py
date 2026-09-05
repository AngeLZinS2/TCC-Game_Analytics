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
from db.session import session_scope
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


def test_desempenho_le_do_banco_e_nao_chama_o_opgg(monkeypatch):
    """O assistente responde com o que ja foi coletado, nao com uma chamada ao
    vivo. `_desempenho_externo` le `fato_estatistica_personagem`; o servidor MCP
    e assunto do coletor, numa rodada agendada."""
    def explode(*_a, **_k):
        raise AssertionError("o assistente nao pode chamar o OP.GG ao vivo")

    monkeypatch.setattr(opgg_mcp, "estatisticas_agentes_valorant", explode)
    monkeypatch.setattr(opgg_mcp, "chamar_ferramenta", explode)

    with session_scope() as sessao:
        # Counter-Strike nao tem `fato_estatistica_personagem` - devolve vazio,
        # sem tocar na rede.
        assert _desempenho_externo(sessao, "counterstrike") == {}
        # Um jogo com coleta devolve dicionario indexado por id_externo.
        valorant = _desempenho_externo(sessao, "valorant")
        assert isinstance(valorant, dict)
        for chave, dados in valorant.items():
            assert chave == chave.lower()
            assert {"nome", "partidas", "vitorias", "winrate", "metricas"} <= dados.keys()


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
        "aaa": {"nome": "Jett", "partidas": 100, "vitorias": 50, "winrate": 50.0,
                "metricas": {"pick_rate": 4.0, "hs": 24.0}},
        "bbb": {"nome": "Clove", "partidas": 300, "vitorias": 156, "winrate": 51.9,
                "metricas": {"pick_rate": 12.2, "hs": 21.0}},
    }

    bloco, serie = _elenco_com_desempenho("VALORANT", "valorant", elenco, desempenho)

    assert bloco.fonte == "opgg"
    corpo = bloco.conteudo
    assert corpo.index("Clove") < corpo.index("Jett")
    # Sem estatistica nao vira zero: vira ausencia declarada.
    assert "Vyse (Sentinela): sem estatistica no OP.GG" in corpo
    # A metrica sai com o rotulo do proprio esporte.
    assert "HS% 21.0%" in corpo
    assert "nao sao do cenario profissional" in corpo
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
