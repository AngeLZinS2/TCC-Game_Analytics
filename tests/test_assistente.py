"""Testes do roteamento de contexto do assistente.

Nao ha chamada de rede aqui: o que se testa e a parte determinista - qual
contexto a pergunta seleciona. A resposta do modelo nao e testavel por
assercao, mas o que ele RECEBE e, e e ai que mora a corretude: um bloco de
contexto que nao entra vira uma resposta "nao sei" com o dado no banco, e um
que entra errado vira um numero certo respondendo a pergunta errada.

A consulta a loja da Steam faz rede e por isso nao e exercitada aqui. O que se
testa dela e o que decide se ela acontece: a extracao do nome e a confirmacao.
Sao essas duas que separam "perguntou de um jogo" de "perguntou do sistema", e
errar ai e o unico jeito de o bloco novo produzir resposta falsa.
"""

from __future__ import annotations

import pytest

from db.session import session_scope
from ml.assistente import (
    GATILHOS,
    INSTRUCAO,
    Bloco,
    _bloco_recomendacao,
    _confirma_nome,
    _genero_pedido,
    _normalizar,
    _pede_recomendacao,
    _recomendacoes,
    _termos_de_jogo,
)


def test_normalizacao_ignora_acento_e_caixa():
    assert _normalizar("Herói") == _normalizar("heroi") == "heroi"
    assert _normalizar("PREVISÃO") == "previsao"
    assert _normalizar("Avaliações") == "avaliacoes"


@pytest.mark.parametrize(
    "pergunta,esperado",
    [
        ("Qual jogo tem mais jogadores simultâneos?", "steam"),
        ("Quantas partidas de Dota foram coletadas?", "partidas"),
        ("Qual herói tem o melhor winrate?", "herois"),
        ("Qual a acurácia do modelo de previsão?", "modelos"),
        ("Como está o sentimento das avaliações?", "sentimento"),
    ],
)
def test_pergunta_aciona_o_bloco_certo(pergunta: str, esperado: str):
    normalizada = _normalizar(pergunta)
    acionados = {
        chave
        for chave, termos in GATILHOS.items()
        if any(_normalizar(termo) in normalizada for termo in termos)
    }
    assert esperado in acionados


def test_gatilhos_funcionam_sem_acento_na_pergunta():
    """Ninguem digita acento numa caixa de busca com pressa."""
    normalizada = _normalizar("qual heroi tem melhor winrate")
    acionados = {
        chave
        for chave, termos in GATILHOS.items()
        if any(_normalizar(termo) in normalizada for termo in termos)
    }
    assert "herois" in acionados


def test_todo_gatilho_tem_termos():
    assert GATILHOS
    for chave, termos in GATILHOS.items():
        assert termos, f"{chave} sem termos"
        assert all(termo.strip() for termo in termos)


def test_instrucao_prende_todo_numero_ao_contexto():
    """O prompt e parte do contrato, e este e o item que nao pode cair.

    A instrucao foi afrouxada de proposito em UM eixo - o modelo agora pode
    falar de jogos que nao temos, qualitativamente. O eixo que NAO afrouxou e o
    numerico: foi ele que transformou um assistente que respondia '20.285
    jogos' num que responde 12. Se alguem remover estas regras achando que
    estao sobrando, este teste avisa.
    """
    assert "TODO NÚMERO" in INSTRUCAO
    assert "Esta regra não tem exceção" in INSTRUCAO
    assert "Não estime" in INSTRUCAO


def test_instrucao_marca_o_conhecimento_geral():
    """Falar de fora do banco e permitido; faze-lo sem marca, nao.

    Sem o prefixo, conhecimento geral e medicao chegam com a mesma cara ao
    leitor - que e exatamente a confusao que o assistente existe para evitar.
    """
    assert "Fora dos dados: " in INSTRUCAO
    assert "PROIBIDO escrever qualquer número" in INSTRUCAO
    assert "LOJA DA STEAM" in INSTRUCAO


@pytest.mark.parametrize(
    "pergunta,esperado",
    [
        ("qual o preco de hollow knight?", "hollow knight"),
        ("o cyberpunk 2077 vale a pena?", "cyberpunk 2077"),
        ("me fale sobre hades", "hades"),
        # A sobra solta juntava palavras nao adjacentes e produzia um termo que
        # nao existe na loja; o recorte em trechos contiguos e o que corrige.
        ("o cyberpunk 2077 vale a pena? ele esta no banco?", "cyberpunk 2077"),
    ],
)
def test_termo_de_jogo_sobra_o_nome(pergunta: str, esperado: str):
    assert _termos_de_jogo(pergunta) == [esperado]


@pytest.mark.parametrize(
    "pergunta",
    [
        "quantos jogos da steam estao no banco?",
        "quais os jogos mais caros do catalogo?",
        "quantas partidas coletamos?",
    ],
)
def test_pergunta_sobre_o_proprio_sistema_nao_vira_busca(pergunta: str):
    """Pergunta sobre NOS nao deve disparar consulta a loja.

    Alem de gastar rede a toa, sobra de pergunta ('mais caros') devolve app
    aleatorio na busca da loja - e um app aleatorio no contexto e uma resposta
    confiante sobre o jogo errado.
    """
    assert _termos_de_jogo(pergunta) == []


def test_nome_precisa_estar_contido_na_pergunta():
    """A confirmacao e por conteudo, nao por semelhanca.

    Mesma contencao do casamento de times em `etl/load_liquipedia.py`: sem ela,
    perguntar de partidas de Dota traria a ficha de 'Dota Underlords', e a
    resposta sairia confiante sobre o jogo errado.
    """
    assert _confirma_nome("Hades", "me fale sobre hades")
    assert _confirma_nome("Portal 2", "qual o preco de portal 2")

    assert not _confirma_nome("Dota Underlords", "quantas partidas de dota temos")
    assert not _confirma_nome("Mais", "quais os jogos mais caros")


@pytest.mark.parametrize(
    "pergunta,esperado",
    [
        ("que jogo de ação você recomenda?", "Action"),
        ("quero um jogo de RPG bom", "RPG"),
        ("tem algum jogo de estratégia?", "Strategy"),
        ("indica um indie", "Indie"),
        ("prefiro jogo gratuito", "Free To Play"),
        ("qual o preço de hollow knight?", None),
    ],
)
def test_genero_pedido(pergunta: str, esperado: str | None):
    assert _genero_pedido(pergunta) == esperado


def test_genero_pedido_nao_casa_substring_dentro_de_outra_palavra():
    """"rpg" so deve casar como token inteiro, nao como pedaco de outra palavra."""
    assert _genero_pedido("quantos jogadores tem esse corpg") is None


@pytest.mark.parametrize(
    "pergunta",
    [
        "o que você me recomenda?",
        "tem alguma sugestão de jogo?",
        "qual jogo vale a pena jogar?",
    ],
)
def test_pede_recomendacao_sem_genero(pergunta: str):
    assert _pede_recomendacao(pergunta)
    assert _genero_pedido(pergunta) is None


def test_pede_recomendacao_falso_para_pergunta_comum():
    assert not _pede_recomendacao("quantos jogos da steam estao no banco?")


def test_recomendacoes_por_genero_vem_do_catalogo_e_ordenadas():
    """Cada candidato precisa ter o genero pedido e vir do melhor pro pior."""
    with session_scope() as sessao:
        candidatos = _recomendacoes(sessao, genero="Action")

    assert candidatos
    for candidato in candidatos:
        assert "Action" in candidato.generos

    notas = [c.nota_avaliacoes or 0 for c in candidatos]
    assert notas == sorted(notas, reverse=True)


def test_bloco_recomendacao_sem_genero_pede_todo_catalogo():
    with session_scope() as sessao:
        bloco, candidatos = _bloco_recomendacao("me recomenda um jogo", sessao)

    assert bloco is not None
    assert bloco.chave == "recomendacao"
    assert candidatos
    assert "catálogo" in bloco.conteudo.lower()


def test_bloco_recomendacao_ausente_sem_pedido_de_recomendacao():
    with session_scope() as sessao:
        bloco, candidatos = _bloco_recomendacao("quantas partidas coletamos?", sessao)

    assert bloco is None
    assert candidatos == []


def test_bloco_recomendacao_genero_nao_reconhecido_cai_no_geral():
    """"Terror" nao esta em `MAPA_GENEROS" - sem genero pra filtrar, o pedido de
    recomendacao ainda dispara, so que sobre o catalogo inteiro (nunca um jogo
    inventado de fora dele)."""
    with session_scope() as sessao:
        bloco, candidatos = _bloco_recomendacao("recomenda um jogo de terror", sessao)

    assert bloco is not None
    assert candidatos
    assert "melhor avaliação geral" in bloco.titulo.lower()


def test_bloco_do_banco_e_bloco_da_loja_se_declaram():
    """A procedencia e campo, nao convencao de titulo.

    A tela pinta os dois de forma diferente e a instrucao manda citar a fonte;
    as duas coisas leem `fonte`.
    """
    assert Bloco(chave="x", titulo="t", conteudo="c").fonte == "banco"
    assert Bloco(chave="x", titulo="t", conteudo="c", fonte="steam").fonte == "steam"
