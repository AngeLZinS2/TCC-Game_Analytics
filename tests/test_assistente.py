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
    PontoSerie,
    SerieAssistente,
    _bloco_extremo_avaliacao,
    _bloco_herois,
    _bloco_partidas,
    _bloco_recomendacao,
    _bloco_sentimento,
    _bloco_steam,
    _confirma_nome,
    _extremo_avaliacao_pedido,
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


def test_normalizacao_remove_simbolo_de_marca():
    """A Steam guarda o nome com simbolo colado ("HELLDIVERS™ 2") - sem
    remover, o nome achado na loja nunca bate com o que a pessoa digitou."""
    assert _normalizar("HELLDIVERS™ 2") == "helldivers 2"
    assert _normalizar("Apex Legends™") == "apex legends"
    assert _normalizar("Rocket League®") == "rocket league"


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
        # Vocabulario de "onde compro isso mais barato" - a pergunta que o
        # painel de preco existe pra responder. Sem estas palavras na lista de
        # vazias, elas grudavam no nome ("helldivers 2 pelo menor") e a busca
        # na loja nao achava nada.
        ("Onde encontro o Helldivers 2 pelo menor preço?", "helldivers 2"),
        ("quero comprar o Hollow Knight pelo menor valor", "hollow knight"),
        ("onde compro elden ring mais barato?", "elden ring"),
        (
            "Call of Duty Modern Warfare III onde encontro pelo menor preço?",
            "call of duty modern warfare iii",
        ),
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


def test_nome_casa_numeral_romano_com_arabico_dos_dois_lados():
    """O bug relatado: a Steam guarda "HELLDIVERS™ 2" (arabico + simbolo de
    marca), mas a pessoa escreve "Helldivers II" (romano) - sem tolerar os
    dois sentidos, a busca acha o jogo certo e o rejeita na confirmacao."""
    assert _confirma_nome("HELLDIVERS™ 2", "o jogo Helldivers II sabe me dizer o preço?")
    # E o sentido inverso: titulo em romano na Steam, pergunta em arabico.
    assert _confirma_nome("Civilization VI", "quanto custa civilization 6?")
    # Continua rejeitando jogo errado - a folga e so no numeral, nao no nome.
    assert not _confirma_nome("HELLDIVERS™ 2", "qual o preço de portal 2?")


def test_nome_casa_apesar_da_pontuacao_do_titulo_oficial():
    """Segundo caso do mesmo problema: o titulo oficial tem pontuacao que
    ninguem digita. "Call of Duty®: Modern Warfare® III" era achado pela
    busca e rejeitado na confirmacao por causa do dois-pontos."""
    cod = "Call of Duty®: Modern Warfare® III"
    assert _confirma_nome(cod, "Call of Duty Modern Warfare III onde acho mais barato?")
    assert _confirma_nome(cod, "quanto custa call of duty: modern warfare iii?")

    # Apostrofo e hifen, o mesmo caso.
    assert _confirma_nome("Marvel's Spider-Man Remastered", "preco de marvels spider man remastered")
    assert _confirma_nome("Half-Life 2", "quanto custa half life 2?")


def test_pontuacao_nao_afrouxa_o_casamento_de_jogo_errado():
    """A folga e so de escrita: DLC e jogo diferente continuam fora."""
    dlc = "Call of Duty®: Modern Warfare® III - Tracer Pack: Underboss Pro Pack"
    assert not _confirma_nome(dlc, "call of duty modern warfare iii preço")
    assert not _confirma_nome("Call of Duty®: Modern Warfare® III", "quanto custa o portal 2?")
    assert not _confirma_nome("Dota Underlords", "quantas partidas de dota temos")


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


def test_bloco_recomendacao_nao_dispara_para_pergunta_de_pior_avaliado():
    """"Qual jogo de ação tem a PIOR avaliação" cita genero mas pede o extremo
    oposto de uma recomendacao - so quem responde e `_bloco_extremo_avaliacao`
    (bug real: as duas perguntas disparavam junto, e a tela mostrava cartao de
    jogo bom do lado da resposta sobre o pior jogo)."""
    with session_scope() as sessao:
        bloco, candidatos = _bloco_recomendacao(
            "qual jogo de ação tem a pior avaliação na Steam?", sessao
        )

    assert bloco is None
    assert candidatos == []


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


@pytest.mark.parametrize(
    "pergunta,esperado",
    [
        ("qual jogo tem a pior avaliação da steam?", "pior"),
        ("qual jogo é o pior avaliado?", "pior"),
        ("qual é o jogo mais mal avaliado de ação?", "pior"),
        ("qual rpg tem a melhor avaliação?", "melhor"),
        ("qual jogo tem mais jogadores?", None),
    ],
)
def test_extremo_avaliacao_pedido(pergunta: str, esperado: str | None):
    assert _extremo_avaliacao_pedido(pergunta) == esperado


def test_bloco_extremo_ausente_sem_pedido_de_extremo():
    """Pergunta comum nao aciona a consulta ao SteamSpy (que faz rede)."""
    assert _bloco_extremo_avaliacao("quantas partidas coletamos?") is None


def test_bloco_extremo_sem_genero_pede_o_genero_em_vez_de_usar_o_catalogo():
    """O bug relatado: "pior avaliação" sem genero nao tem como responder
    sobre TODA a Steam - a resposta certa e pedir o genero de volta, nao
    silenciosamente usar os 20 e poucos jogos do nosso catalogo como se
    fossem "os piores da Steam"."""
    bloco = _bloco_extremo_avaliacao("qual é o jogo com a pior avaliação?")

    assert bloco is not None
    assert bloco.chave == "extremo_avaliacao"
    assert "falta o genero" in _normalizar(bloco.conteudo)
    # Nao faz chamada nenhuma ao SteamSpy - a fonte fica "banco" (o default),
    # porque este bloco especifico e so a instrucao de pedir o genero.
    assert bloco.fonte == "banco"


def test_bloco_do_banco_e_bloco_da_loja_se_declaram():
    """A procedencia e campo, nao convencao de titulo.

    A tela pinta os dois de forma diferente e a instrucao manda citar a fonte;
    as duas coisas leem `fonte`.
    """
    assert Bloco(chave="x", titulo="t", conteudo="c").fonte == "banco"
    assert Bloco(chave="x", titulo="t", conteudo="c", fonte="steam").fonte == "steam"


def test_todo_construtor_de_bloco_devolve_par_bloco_serie():
    """O contrato do laco de `montar_contexto`: os quatro construtores da lista
    devolvem `(Bloco, SerieAssistente | None)`.

    Existe porque a violacao ja aconteceu: `_bloco_partidas` ficou devolvendo
    um `Bloco` solto depois da mudanca, e o `bloco, serie = ...` estourou
    `TypeError: cannot unpack non-iterable Bloco object` - em producao, na
    primeira pergunta que citava "partidas". Nenhum teste passava pelo laco,
    entao a suite inteira ficou verde com a rota quebrada.
    """
    construtores = (_bloco_steam, _bloco_partidas, _bloco_herois, _bloco_sentimento)

    with session_scope() as sessao:
        for construtor in construtores:
            resultado = construtor(sessao)

            assert isinstance(resultado, tuple), f"{construtor.__name__} nao devolveu tupla"
            bloco, serie = resultado
            assert isinstance(bloco, Bloco)
            assert serie is None or isinstance(serie, SerieAssistente)
            if serie is not None:
                # Uma serie sem unidade nao da pra rotular no eixo do grafico.
                assert serie.chave and serie.titulo and serie.unidade
                assert all(isinstance(p, PontoSerie) for p in serie.itens)
