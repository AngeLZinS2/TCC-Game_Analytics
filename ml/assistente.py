"""Assistente que responde perguntas sobre os dados coletados.

**O modelo nao consulta o banco.** Ele recebe um contexto ja montado aqui, a
partir de consultas SQL fixas, e a instrucao de responder so com o que esta ali.

Essa arquitetura nao foi a primeira escolha - foi a que os dados de teste
impuseram. A ideia inicial era dar ferramentas ao modelo e deixa-lo consultar o
que precisasse. Os modelos gratuitos disponiveis no OpenRouter ignoram
`tools`, e ignoram inclusive `tool_choice: "required"`: perguntados "quantos
jogos da Steam estao sendo monitorados", respondem "20.285" com toda a
confianca, sem chamar nada. O numero verdadeiro e 12.

Um assistente que inventa numero e pior que assistente nenhum num projeto cujo
proposito e a integridade do dado. Dai as tres decisoes deste modulo:

1. **A recuperacao acontece antes**, em Python, com SQL escrito a mao. Nao ha
   texto-para-SQL nem execucao de consulta gerada pelo modelo.
2. **O contexto vai junto na resposta** (`blocos`), e a tela mostra. Todo numero
   exibido pode ser conferido contra a fonte.
3. **A instrucao proibe extrapolar.** Sem o dado no contexto, a resposta certa e
   dizer que o dado nao esta ali.

**O chao foi alargado, nao removido.** O banco nao pode conter a Steam inteira,
muito menos os jogos que nem sao da Steam - e responder "nao sei" sobre um jogo
que existe seria uma limitacao do nosso armazenamento vestida de resposta. Entao
o contexto passou a ter duas fontes, e cada bloco declara a sua:

* `banco` - o que a plataforma coletou e mediu.
* `steam` - a loja consultada AGORA, para o jogo citado na pergunta, esteja ele
  no nosso banco ou nao.

E ha um terceiro nivel, que nao vira bloco porque nao tem fonte: um jogo de
console ou de outra loja, sobre o qual nao existe dado nenhum aqui. Para esses a
instrucao libera o conhecimento geral do modelo - **mas so qualitativo, e com
marca explicita**. Numero continua vindo so de bloco. Essa e a linha exata: o
que quebrou o assistente antes nao foi ele falar de jogos, foi ele inventar
"20.285" com cara de medicao. Descrever o que e Zelda nao corre esse risco;
dizer quantas copias Zelda vendeu corre.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

import requests
from sqlalchemy import Integer, cast, desc, func, select

from collectors import steam_loja
from config import get_settings
from db.models import (
    DimJogoSteam,
    DimPartida,
    DimPersonagem,
    FatoAvaliacaoSteam,
    FatoPartidaJogador,
    FatoSnapshotJogoSteam,
)
from db.session import session_scope
from ml.confronto import carregar_relatorio as relatorio_confronto
from ml.sentimento import carregar_metricas as metricas_sentimento

logger = logging.getLogger(__name__)

INSTRUCAO = """\
Você é o assistente de dados do Gaming Analytics, uma plataforma de coleta e \
análise de dados de jogos e esports.

O CONTEXTO abaixo vem em blocos, e cada bloco declara a FONTE dele:

- NOSSO BANCO: dados que a plataforma coletou, mediu e armazenou.
- LOJA DA STEAM: consultada agora, ao vivo, para o jogo citado na pergunta - \
pode ser um jogo que não está no nosso banco.

REGRAS, em ordem de prioridade:

1. TODO NÚMERO que você escrever precisa aparecer no CONTEXTO, literalmente. \
Não estime, não calcule média que não esteja calculada, não converta unidade, \
não some valores que não estejam somados. Esta regra não tem exceção.
2. Diga de onde veio o dado quando ele vier da loja da Steam - uma frase curta \
como "segundo a loja da Steam, agora" basta. Quem lê precisa distinguir o que \
nós medimos do que é dado externo.
3. Se a pergunta for sobre um jogo que NÃO está no contexto (um jogo de \
console, de outra loja, ou que a busca não encontrou), você PODE usar seu \
conhecimento geral - mas apenas de forma qualitativa: que jogo é, de que \
gênero, de quem é, como se compara. Comece essas frases com "Fora dos dados: ". \
Nesse modo é PROIBIDO escrever qualquer número: nada de vendas, notas, número \
de jogadores, datas ou preços.
4. Quando faltar o dado para responder, diga o que falta e sugira qual tela do \
dashboard tem esse dado. Não preencha a lacuna com suposição.
5. Responda em português do Brasil, direto, em no máximo 6 linhas. Sem \
saudação e sem repetir a pergunta.
6. Os dados do nosso banco são de uma coleta específica, não são "ao vivo". Se \
a pergunta sugerir tempo real, diga de quando é o dado.
7. Se a pergunta for sobre um jogo DA STEAM que ainda não está no nosso banco, \
o caminho real é este: buscar o jogo pelo nome nas telas "Jogos da Steam" ou \
"Recomendações por Reviews" e clicar no resultado - a coleta acontece na hora, \
em segundos. Não invente outra tela, outro cadastro nem outro procedimento. \
Jogos que não são da Steam não podem ser coletados por esta plataforma.
8. Quando houver um bloco "Recomendação (...)", a resposta PRECISA escolher \
entre os jogos listados nele, citando nome, nota e jogadores como aparecem lá \
- nunca um jogo de fora dessa lista, mesmo que ele exista no restante do \
CONTEXTO ou no seu conhecimento geral. Se o bloco disser que não há \
candidato, diga isso e não ofereça um jogo substituto.
"""


@dataclass
class Bloco:
    """Um pedaco de contexto: o que e, de onde veio, e o texto para o modelo.

    `fonte` nao e enfeite. A tela pinta o bloco do banco e o bloco da loja de
    formas diferentes, e a instrucao manda o modelo citar a procedencia - sem
    esse campo, um numero medido por nos e um numero lido da loja chegariam ao
    leitor com a mesma cara.
    """

    chave: str
    titulo: str
    conteudo: str
    fonte: str = "banco"


@dataclass
class JogoRecomendado:
    """Um candidato de `_recomendacoes`, ja pronto pra tela desenhar um cartao.

    Existe separado do texto do modelo de proposito: a tela NAO tenta advinhar
    de qual jogo o texto fala (analisar a resposta em busca de um nome e
    exatamente o tipo de inferencia fragil que este projeto evita em outro
    lugar). O cartao vem de quem decidiu o ranking - o Python -, nao de quem
    so descreve o resultado - o modelo.
    """

    app_id: int
    nome: str
    generos: list[str]
    nota_avaliacoes: float | None
    jogadores_simultaneos: int | None
    preco: float | None
    moeda: str | None
    gratuito: bool | None


@dataclass
class Resposta:
    pergunta: str
    resposta: str
    modelo: str
    blocos: list[Bloco] = field(default_factory=list)
    #: Os jogos que uma pergunta de recomendacao selecionou - ver `_recomendacoes`.
    #: Vazio fora desse caso. A tela usa isto para desenhar cartao com imagem,
    #: em vez de confiar em texto livre pra saber qual jogo foi recomendado.
    recomendacoes: list[JogoRecomendado] = field(default_factory=list)
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


class AssistenteIndisponivel(RuntimeError):
    """Falta chave, ou o provedor recusou a chamada."""


# ---------------------------------------------------------------------------
# Montagem do contexto
# ---------------------------------------------------------------------------


def _normalizar(texto: str) -> str:
    """Minuscula e sem acento - para casar 'herói' com 'heroi'."""
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def _bloco_geral(sessao) -> Bloco:
    jogos = sessao.scalar(select(func.count()).select_from(DimJogoSteam)) or 0
    snapshots = sessao.scalar(select(func.count()).select_from(FatoSnapshotJogoSteam)) or 0
    partidas = sessao.scalar(select(func.count()).select_from(DimPartida)) or 0
    fatos = sessao.scalar(select(func.count()).select_from(FatoPartidaJogador)) or 0
    herois = sessao.scalar(select(func.count()).select_from(DimPersonagem)) or 0
    avaliacoes = sessao.scalar(select(func.count()).select_from(FatoAvaliacaoSteam)) or 0
    ultima = sessao.scalar(select(func.max(FatoSnapshotJogoSteam.janela_coleta)))

    linhas = [
        f"Jogos da Steam monitorados: {jogos}",
        f"Snapshots da Steam (serie temporal): {snapshots}",
        f"Partidas profissionais coletadas: {partidas}",
        f"Linhas de fato jogador-por-partida: {fatos}",
        f"Herois na dimensao de personagem: {herois}",
        f"Avaliacoes da Steam com texto: {avaliacoes}",
        f"Ultima janela de coleta da Steam: {ultima:%d/%m/%Y %H:%M UTC}" if ultima else "",
    ]
    return Bloco("geral", "Volumes do banco", "\n".join(l for l in linhas if l))


def _bloco_steam(sessao) -> Bloco:
    recentes = (
        select(FatoSnapshotJogoSteam)
        .distinct(FatoSnapshotJogoSteam.app_id)
        .order_by(
            FatoSnapshotJogoSteam.app_id, desc(FatoSnapshotJogoSteam.janela_coleta)
        )
        .subquery()
    )

    linhas = []
    for nome, generos, jogadores, nota, preco, moeda in sessao.execute(
        select(
            DimJogoSteam.nome,
            DimJogoSteam.generos,
            recentes.c.jogadores_simultaneos,
            recentes.c.nota_avaliacoes,
            recentes.c.preco_no_momento,
            recentes.c.moeda,
        )
        .join(recentes, recentes.c.app_id == DimJogoSteam.app_id)
        .order_by(desc(recentes.c.jogadores_simultaneos))
    ):
        preco_texto = (
            "Gratuito" if preco is not None and preco == 0
            else f"{moeda or ''} {preco}".strip() if preco is not None
            else "sem preco"
        )
        linhas.append(
            f"{nome} ({', '.join(generos or []) or 'genero nao coletado'}): "
            f"{jogadores or 0} jogadores simultaneos, "
            f"{nota or '-'}% de avaliacoes positivas, {preco_texto}"
        )

    return Bloco(
        "steam",
        "Catalogo da Steam (ultimo snapshot de cada jogo)",
        "\n".join(linhas) or "Nenhum jogo coletado.",
    )


# ---------------------------------------------------------------------------
# Recomendacao por genero (ou "melhor avaliado", sem genero)
# ---------------------------------------------------------------------------

#: Portugues -> o genero exato como a Steam guarda em `dim_jogo_steam.generos`
#: (`appdetails.genres[].description`, em ingles). Cada chave de uma palavra so
#: casa por TOKEN inteiro (ver `_genero_pedido`); as de duas ou mais, por trecho
#: contiguo - o mesmo criterio de `_termos_de_jogo`, pela mesma razao: "rpg"
#: dentro de outra palavra nao deveria casar, "acesso antecipado" sim.
MAPA_GENEROS: dict[str, str] = {
    "acao": "Action",
    "aventura": "Adventure",
    "rpg": "RPG",
    "estrategia": "Strategy",
    "simulacao": "Simulation",
    "simulador": "Simulation",
    "indie": "Indie",
    "multijogador": "Massively Multiplayer",
    "mmo": "Massively Multiplayer",
    "massivo": "Massively Multiplayer",
    "acesso antecipado": "Early Access",
    "early access": "Early Access",
    "gratuito": "Free To Play",
    "gratis": "Free To Play",
    "f2p": "Free To Play",
}

#: Frases que pedem uma recomendacao mesmo sem nomear genero nenhum - "me
#: recomenda um jogo" vira "os mais bem avaliados do catalogo inteiro".
GATILHOS_RECOMENDACAO = (
    "recomenda", "recomendo", "recomendacao",
    "sugere", "sugestao", "indica", "indicacao",
    "vale a pena jogar", "devo jogar",
)


def _genero_pedido(pergunta: str) -> str | None:
    """O genero da Steam que a pergunta pede, se houver algum reconhecivel."""
    normalizada = _normalizar(pergunta)
    tokens = set(re.findall(r"[a-z0-9]+", normalizada))
    for chave, genero in MAPA_GENEROS.items():
        if " " in chave:
            if chave in normalizada:
                return genero
        elif chave in tokens:
            return genero
    return None


def _pede_recomendacao(pergunta: str) -> bool:
    normalizada = _normalizar(pergunta)
    return any(_normalizar(gatilho) in normalizada for gatilho in GATILHOS_RECOMENDACAO)


def _recomendacoes(
    sessao, genero: str | None, limite: int = 3
) -> list[JogoRecomendado]:
    """Os melhores candidatos do NOSSO catalogo - nunca um jogo de fora dele.

    Ranking por nota de avaliacao e, empatando, por jogadores simultaneos
    agora - os dois numeros que a tela de Jogos da Steam ja usa para "o que
    esta bem" e "o que esta em alta". Nada aqui e decidido pelo modelo: o
    Python escolhe os candidatos, o modelo so descreve o que o Python achou.
    """
    recentes = (
        select(FatoSnapshotJogoSteam)
        .distinct(FatoSnapshotJogoSteam.app_id)
        .order_by(
            FatoSnapshotJogoSteam.app_id, desc(FatoSnapshotJogoSteam.janela_coleta)
        )
        .subquery()
    )

    consulta = (
        select(
            DimJogoSteam.app_id,
            DimJogoSteam.nome,
            DimJogoSteam.generos,
            DimJogoSteam.gratuito,
            recentes.c.nota_avaliacoes,
            recentes.c.jogadores_simultaneos,
            recentes.c.preco_no_momento,
            recentes.c.moeda,
        )
        .join(recentes, recentes.c.app_id == DimJogoSteam.app_id)
    )
    if genero:
        consulta = consulta.where(DimJogoSteam.generos.any(genero))
    consulta = consulta.order_by(
        desc(func.coalesce(recentes.c.nota_avaliacoes, 0)),
        desc(func.coalesce(recentes.c.jogadores_simultaneos, 0)),
    ).limit(limite)

    return [
        JogoRecomendado(
            app_id=app_id,
            nome=nome,
            generos=generos or [],
            nota_avaliacoes=float(nota) if nota is not None else None,
            jogadores_simultaneos=jogadores,
            preco=float(preco) if preco is not None else None,
            moeda=moeda,
            gratuito=gratuito,
        )
        for app_id, nome, generos, gratuito, nota, jogadores, preco, moeda in sessao.execute(
            consulta
        )
    ]


def _bloco_recomendacao(
    pergunta: str, sessao
) -> tuple[Bloco | None, list[JogoRecomendado]]:
    """Bloco + lista estruturada para uma pergunta de recomendacao.

    Devolve `(None, [])` quando a pergunta nao pede recomendacao nenhuma - o
    caso comum. Quando pede, o bloco e SEMPRE gerado, mesmo sem candidato: a
    regra 8 da instrucao proibe o modelo de inventar um jogo pra preencher a
    lacuna, e a unica forma de garantir isso e a lacuna aparecer explicita no
    contexto.
    """
    genero = _genero_pedido(pergunta)
    if genero is None and not _pede_recomendacao(pergunta):
        return None, []

    candidatos = _recomendacoes(sessao, genero)
    rotulo = f"gênero {genero}" if genero else "melhor avaliação geral"

    if not candidatos:
        return (
            Bloco(
                "recomendacao",
                f"Recomendação ({rotulo})",
                f"Nenhum jogo de {rotulo} no nosso catálogo. Diga que não há "
                "candidato aqui - não substitua por um jogo de fora do catálogo.",
            ),
            [],
        )

    linhas = [
        f"Candidatos do NOSSO catálogo para {rotulo}, do melhor pro pior "
        "(nota de avaliação e depois jogadores simultâneos agora). "
        "Recomende só entre estes:",
    ]
    for c in candidatos:
        preco_texto = (
            "Gratuito"
            if c.gratuito
            else f"{c.moeda or ''} {c.preco}".strip() if c.preco is not None
            else "sem preço"
        )
        linhas.append(
            f"- {c.nome}: {c.nota_avaliacoes if c.nota_avaliacoes is not None else '-'}% "
            f"de avaliações positivas, {c.jogadores_simultaneos or 0} jogadores agora, "
            f"gêneros {', '.join(c.generos) or '-'}, {preco_texto}"
        )

    return (
        Bloco("recomendacao", f"Recomendação ({rotulo}) - catálogo próprio", "\n".join(linhas)),
        candidatos,
    )


def _bloco_partidas(sessao) -> Bloco:
    total = sessao.scalar(select(func.count()).select_from(DimPartida)) or 0
    duracao = sessao.scalar(select(func.avg(DimPartida.duracao_segundos)))
    # Contar linhas de fato daria dez vezes o numero de partidas - cada partida
    # tem dez jogadores. O DISTINCT sobre id_partida e o que conta partidas.
    vitorias_radiant = sessao.scalar(
        select(func.count(func.distinct(FatoPartidaJogador.id_partida))).where(
            FatoPartidaJogador.equipe == "radiant",
            FatoPartidaJogador.vitoria.is_(True),
        )
    ) or 0

    ligas = sessao.execute(
        select(DimPartida.liga_nome, func.count())
        .where(DimPartida.liga_nome.is_not(None))
        .group_by(DimPartida.liga_nome)
        .order_by(func.count().desc())
        .limit(6)
    ).all()

    percentual = round(100 * vitorias_radiant / total, 1) if total else 0
    linhas = [
        f"Partidas coletadas: {total}",
        f"Duracao media: {round(float(duracao) / 60, 1)} minutos" if duracao else "",
        f"Partidas vencidas pelo lado Radiant: {vitorias_radiant} ({percentual}%)",
        "Torneios: " + ", ".join(f"{nome.strip()} ({n} partidas)" for nome, n in ligas),
    ]
    return Bloco("partidas", "Dominio de partidas (Dota 2)", "\n".join(l for l in linhas if l))


def _bloco_herois(sessao) -> Bloco:
    vitorias = func.sum(cast(FatoPartidaJogador.vitoria, Integer))
    partidas = func.count()

    consulta = (
        select(
            DimPersonagem.nome,
            partidas.label("partidas"),
            (100.0 * vitorias / partidas).label("winrate"),
        )
        .join(
            DimPersonagem,
            DimPersonagem.id_personagem == FatoPartidaJogador.id_personagem,
        )
        .group_by(DimPersonagem.nome)
        .having(partidas >= 5)
        .order_by(desc("winrate"))
    )
    linhas = sessao.execute(consulta).all()

    def formatar(grupo):
        return "\n".join(
            f"{nome}: {round(float(winrate), 1)}% de winrate em {n} partidas"
            for nome, n, winrate in grupo
        )

    return Bloco(
        "herois",
        "Herois com 5+ partidas (melhores e piores winrates)",
        formatar(linhas[:8]) + "\n...\n" + formatar(linhas[-8:])
        if len(linhas) > 16
        else formatar(linhas),
    )


def _bloco_modelos() -> Bloco:
    """As metricas do modelo de confronto entre equipes.

    Este bloco descrevia o modelo de previsao por minuto, removido do projeto
    junto das telas que o serviam. O gatilho continua o mesmo - perguntas sobre
    "modelo", "acuracia", "ROC-AUC" - porque a pergunta nao mudou; mudou qual
    modelo responde por ela. Sao dois os que restaram, e o de sentimento ja vai
    no bloco proprio dele.

    A validacao vem inteira, inclusive quando e ruim. O relatorio deste modelo
    diz que ele NAO bate a taxa base, e omitir isso aqui faria o assistente
    vender uma confianca que o numero nao sustenta.
    """
    relatorio = relatorio_confronto()
    if relatorio is None:
        return Bloco(
            "modelos",
            "Modelo de confronto",
            "Nenhum modelo de confronto ajustado ainda "
            "(rode `python cli.py train-confronto`).",
        )

    validacao = relatorio.get("validacao") or {}
    linhas = [
        "Alvo: qual das duas equipes vence um confronto profissional.",
        f"Metodo: {relatorio['metodo']}.",
        f"Ajustado sobre {relatorio['confrontos']} confrontos entre "
        f"{relatorio['equipes']} equipes.",
        f"Regularizacao escolhida por validacao cruzada dentro do treino: "
        f"C={relatorio['regularizacao_C']}.",
    ]

    if validacao.get("suficiente"):
        linhas += [
            "Validacao temporal (walk-forward), "
            f"{validacao['avaliadas']} partidas de teste:",
            f"  acuracia {round(validacao['acuracia'] * 100, 1)}% "
            f"(margem de erro {round(validacao['margem_erro'] * 100, 1)} pontos)",
            f"  taxa base, que um chute constante acertaria: "
            f"{round(validacao['taxa_base'] * 100, 1)}%",
            f"  ROC-AUC {round(validacao['roc_auc'], 3)}, "
            f"log-loss {round(validacao['log_loss'], 4)}",
        ]
        if validacao["acuracia"] <= validacao["taxa_base"]:
            linhas.append(
                "  ATENCAO: a acuracia nao supera a taxa base. Com esta amostra o "
                "modelo NAO demonstra prever melhor que o chute, e a resposta "
                "precisa dizer isso."
            )
    else:
        linhas.append(
            "Amostra pequena demais para validar: as probabilidades sao descritivas, "
            "nao ha metrica de acerto para citar."
        )

    return Bloco("modelos", "Modelo de confronto entre equipes", "\n".join(linhas))


def _bloco_sentimento(sessao) -> Bloco:
    relatorio = metricas_sentimento()
    linhas: list[str] = []

    if relatorio is not None:
        conjunto = relatorio["conjunto"]
        linhas += [
            "Alvo: o polegar do proprio autor da avaliacao (voted_up).",
            f"Treinado sobre {conjunto['avaliacoes']} avaliacoes em {relatorio['idioma']}, "
            f"de {conjunto['jogos']} jogos.",
            f"Taxa base (avaliacoes positivas): {round(conjunto['taxa_base'] * 100, 1)}%",
            f"Modelo servido: {relatorio['modelo_ativo']} (maior ROC-AUC).",
        ]
        for modelo in relatorio["modelos"]:
            linhas.append(
                f"{modelo['nome']}: acuracia {round(modelo['acuracia'] * 100, 1)}%, "
                f"balanceada {round(modelo['acuracia_balanceada'] * 100, 1)}%, "
                f"ROC-AUC {round(modelo['roc_auc'], 4)}"
            )

    positivas = func.sum(cast(FatoAvaliacaoSteam.recomendado, Integer))
    por_jogo = sessao.execute(
        select(DimJogoSteam.nome, func.count(), positivas)
        .join(FatoAvaliacaoSteam, FatoAvaliacaoSteam.app_id == DimJogoSteam.app_id)
        .group_by(DimJogoSteam.nome)
        .order_by(func.count().desc())
    ).all()

    if por_jogo:
        linhas.append("Recomendacao observada por jogo (rotulo real, nao previsao):")
        for nome, total, pos in por_jogo:
            linhas.append(
                f"  {nome}: {round(100 * float(pos or 0) / total, 1)}% positivas "
                f"em {total} avaliacoes"
            )

    return Bloco(
        "sentimento",
        "Sentimento das avaliacoes",
        "\n".join(linhas) or "Nenhuma avaliacao coletada.",
    )


#: Palavras que ligam cada bloco. O roteamento e por palavra-chave de proposito:
#: pedir ao modelo para escolher os blocos seria confiar nele exatamente onde
#: ele ja se mostrou pouco confiavel.
#: Palavras que a pergunta traz por ser uma pergunta, ou por falar do nosso
#: proprio sistema. Nenhuma ajuda a identificar um jogo, e todas atrapalham:
#: sobra delas que a busca da loja devolve resultado aleatorio.
PALAVRAS_VAZIAS = frozenset(
    """
    qual quais quanto quantos quanta quantas quem onde quando como porque
    o a os as um uma uns umas de do da dos das em no na nos nas ao aos pra para
    e ou que se com sem sobre mais menos muito pouco tem temos ha tinha existe
    existem esta estao sao era foi ser sendo vale pena bom boa bons boas ruim
    ruins melhor melhores pior piores caro caros barato baratos legal
    me diga fale mostra mostre mostrar traz traga trazer diz dizer sabe saber
    quero queria gostaria preciso poderia pode voce acha acho achamos
    coletamos temos usamos fizemos ele ela eles elas isso isto esse essa
    aquele aquela aqui ali la tambem ainda ja so apenas entao
    banco dados dado base coletado coletados coletada coletadas coleta coletar
    nosso nossa nossos nossas meu minha sistema plataforma dashboard painel
    tela telas projeto tabela
    jogo jogos game games steam catalogo loja
    partida partidas heroi herois jogador jogadores time times
    avaliacao avaliacoes review reviews nota notas preco precos valor custa
    modelo modelos previsao previsoes acuracia recomendacao recomendacoes
    """.split()
)

#: Um nome de jogo com menos que isto ("Ori", "Fez") existe, mas casar com dois
#: caracteres traria lixo a cada pergunta.
MINIMO_DO_TERMO = 3

#: Quantos trechos tentar na loja antes de desistir. Cada um e uma chamada HTTP,
#: e a partir do terceiro os candidatos ja sao restos improvaveis da frase.
MAXIMO_DE_TENTATIVAS = 2


def _termos_de_jogo(pergunta: str) -> list[str]:
    """Os trechos da pergunta que podem ser nome de jogo, do mais longo ao menor.

    Nao e reconhecimento de entidade: e subtracao seguida de recorte. Tira-se
    da pergunta tudo que e vocabulario de pergunta e vocabulario do nosso
    dominio, e o que sobra vira candidato - mas **so em trechos contiguos**.

    A contiguidade e o que faz funcionar. Juntar as sobras soltas numa string
    so produzia termos que nao existem: "o cyberpunk 2077 vale a pena, ele esta
    no banco?" virava "cyberpunk 2077 ele", que a loja nao acha. Em trechos, o
    mesmo texto da ["cyberpunk 2077"], que ela acha na hora.

    Ordena do mais longo para o mais curto porque o trecho maior e o mais
    especifico: entre "hollow knight" e "hollow", o primeiro erra menos.
    """
    trechos: list[list[str]] = [[]]
    for token in re.findall(r"[a-z0-9]+", _normalizar(pergunta)):
        if token in PALAVRAS_VAZIAS:
            if trechos[-1]:
                trechos.append([])
        else:
            trechos[-1].append(token)

    candidatos = [" ".join(t) for t in trechos if t]
    candidatos = [c for c in candidatos if len(c) >= MINIMO_DO_TERMO]
    candidatos.sort(key=len, reverse=True)
    return candidatos[:MAXIMO_DE_TENTATIVAS]


def _confirma_nome(nome: str, pergunta: str) -> bool:
    """O nome achado na loja precisa estar DENTRO da pergunta, nao parecer com ela.

    Contencao deliberada, e a mesma do casamento de times em
    `etl/load_liquipedia.py`: buscar "mais caros" na loja devolve algum app, e
    aceitar esse app produziria uma resposta confiante sobre o jogo errado -
    que e pior que nao responder. Por isso a exigencia e de conter o nome
    inteiro, contiguo, e nao de parecer.
    """
    alvo = _normalizar(nome)
    if len(alvo) < MINIMO_DO_TERMO or alvo not in _normalizar(pergunta):
        return False

    # Um app chamado "Mais" casaria com quase toda pergunta em portugues.
    return any(t not in PALAVRAS_VAZIAS for t in re.findall(r"[a-z0-9]+", alvo))


def _texto_da_lista(itens: Any, campo: str) -> str:
    """Junta `[{'description': 'Action'}, ...]` num 'Action, Indie'."""
    if not isinstance(itens, list):
        return ""
    nomes = [i.get(campo) for i in itens if isinstance(i, dict) and i.get(campo)]
    return ", ".join(str(n) for n in nomes)


def _bloco_steam_ao_vivo(pergunta: str, sessao) -> Bloco | None:
    """Consulta a loja da Steam sobre o jogo citado na pergunta.

    Devolve `None` sempre que a identificacao nao for segura - sem termo, sem
    resultado, ou com resultado que nao bate com a pergunta. O assistente entao
    se comporta como antes, respondendo pelo banco: perder o bloco custa uma
    resposta mais pobre, enquanto um bloco errado custa uma resposta falsa.
    """
    escolhido = None
    for termo in _termos_de_jogo(pergunta):
        achados = steam_loja.buscar(termo)
        escolhido = next(
            (
                item
                for item in achados
                if _confirma_nome(str(item.get("name", "")), pergunta)
            ),
            None,
        )
        if escolhido is not None:
            break

    if escolhido is None:
        return None

    app_id = int(escolhido["id"])
    nome = str(escolhido["name"])

    dados = steam_loja.ficha(app_id) or {}
    resumo = steam_loja.resumo_avaliacoes(app_id) or {}

    no_banco = sessao.scalar(
        select(DimJogoSteam.app_id).where(DimJogoSteam.app_id == app_id)
    )
    coletadas = 0
    if no_banco:
        coletadas = (
            sessao.scalar(
                select(func.count())
                .select_from(FatoAvaliacaoSteam)
                .where(FatoAvaliacaoSteam.app_id == app_id)
            )
            or 0
        )

    procedencia = (
        f"Este jogo ESTA no nosso banco ({coletadas} avaliacoes com texto coletadas)."
        if no_banco
        else "Este jogo NAO esta no nosso banco: nao ha avaliacoes coletadas, nem "
        "serie temporal, nem previsao do modelo sobre ele."
    )

    preco = dados.get("price_overview") or {}
    lancamento = dados.get("release_date") or {}
    total = resumo.get("total_reviews")
    positivas = resumo.get("total_positive")

    linhas = [
        "FONTE: loja da Steam, consultada agora (dado externo, nao medido por nos).",
        procedencia,
        "",
        f"Nome: {nome}",
        f"AppID: {app_id}",
        f"Desenvolvedora: {', '.join(dados.get('developers') or [])}",
        f"Generos: {_texto_da_lista(dados.get('genres'), 'description')}",
        f"Lancamento: {lancamento.get('date', '')}",
        f"Gratuito: {'sim' if dados.get('is_free') else 'nao'}",
        f"Preco na loja: {preco.get('final_formatted', '')}",
        f"Avaliacoes na Steam (total): {total if total is not None else ''}",
        f"Avaliacoes positivas: {positivas if positivas is not None else ''}",
        f"Classificacao da Steam: {resumo.get('review_score_desc', '')}",
    ]

    # Linha sem valor e ruido que o modelo tenta interpretar; fora.
    conteudo = "\n".join(l for l in linhas if not l.rstrip().endswith(":"))

    return Bloco(
        chave="steam_ao_vivo",
        titulo=f"{nome} - loja da Steam, ao vivo",
        conteudo=conteudo,
        fonte="steam",
    )


GATILHOS: dict[str, tuple[str, ...]] = {
    "steam": ("steam", "jogo", "jogos", "preco", "preço", "catalogo", "catálogo",
              "jogadores simultaneos", "ccu", "genero", "gênero", "desconto"),
    "partidas": ("partida", "partidas", "dota", "torneio", "liga", "duracao",
                 "duração", "radiant", "dire", "esport"),
    "herois": ("heroi", "herói", "herois", "heróis", "winrate", "personagem", "meta"),
    "modelos": ("modelo", "modelos", "previsao", "previsão", "prever", "acuracia",
                "acurácia", "roc", "auc", "treino", "machine learning", "ml"),
    "sentimento": ("sentimento", "avaliacao", "avaliação", "avaliacoes", "avaliações",
                   "review", "reviews", "positiva", "negativa", "nlp"),
}


@dataclass
class ContextoMontado:
    blocos: list[Bloco]
    #: Populado so quando a pergunta pede recomendacao - ver `_bloco_recomendacao`.
    recomendacoes: list[JogoRecomendado] = field(default_factory=list)


def montar_contexto(pergunta: str) -> ContextoMontado:
    """Escolhe os blocos relevantes para a pergunta.

    O bloco geral entra sempre: e barato e responde as perguntas de contagem,
    que sao a maioria. Quando nada casa, entram todos - vale gastar contexto
    para nao responder "nao sei" tendo o dado.

    Por cima disso, dois blocos independem dos gatilhos por palavra e sao
    sempre tentados: a loja ao vivo (se a pergunta nomear um jogo identificavel)
    e a recomendacao (se a pergunta pedir uma, com ou sem genero). Nenhum dos
    dois precisa da palavra "steam" nem "avaliacao" pra disparar.
    """
    normalizada = _normalizar(pergunta)

    construtores: dict[str, Callable[[Any], Bloco]] = {
        "steam": _bloco_steam,
        "partidas": _bloco_partidas,
        "herois": _bloco_herois,
        "sentimento": _bloco_sentimento,
    }

    escolhidos = {
        chave
        for chave, termos in GATILHOS.items()
        if any(_normalizar(termo) in normalizada for termo in termos)
    }
    if not escolhidos:
        escolhidos = set(GATILHOS)

    with session_scope() as sessao:
        blocos = [_bloco_geral(sessao)]
        for chave in ("steam", "partidas", "herois", "sentimento"):
            if chave in escolhidos:
                blocos.append(construtores[chave](sessao))

        ao_vivo = _bloco_steam_ao_vivo(pergunta, sessao)
        if ao_vivo is not None:
            blocos.append(ao_vivo)

        recomendacao, recomendacoes = _bloco_recomendacao(pergunta, sessao)
        if recomendacao is not None:
            blocos.append(recomendacao)

    if "modelos" in escolhidos:
        blocos.append(_bloco_modelos())

    return ContextoMontado(
        blocos=[bloco for bloco in blocos if bloco.conteudo.strip()],
        recomendacoes=recomendacoes,
    )


# ---------------------------------------------------------------------------
# Chamada ao provedor
# ---------------------------------------------------------------------------


def perguntar(pergunta: str) -> Resposta:
    """Monta o contexto, chama o modelo e devolve resposta + contexto usado."""
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise AssistenteIndisponivel(
            "OPENROUTER_API_KEY nao configurada. Defina no .env para usar o assistente."
        )

    contexto_montado = montar_contexto(pergunta)
    blocos = contexto_montado.blocos
    contexto = "\n\n".join(
        f"### {bloco.titulo}\n{bloco.conteudo}" for bloco in blocos
    )

    corpo = {
        "model": settings.openrouter_model,
        "max_tokens": 700,
        # Temperatura baixa: a tarefa e reproduzir numeros do contexto, nao
        # variar a redacao. Criatividade aqui so aumenta a chance de inventar.
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": INSTRUCAO},
            {
                "role": "user",
                "content": f"CONTEXTO:\n{contexto}\n\nPERGUNTA: {pergunta}",
            },
        ],
    }

    try:
        resposta = requests.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json=corpo,
            timeout=settings.openrouter_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise AssistenteIndisponivel(
            f"nao foi possivel falar com o OpenRouter: {type(exc).__name__}"
        ) from exc

    if resposta.status_code != 200:
        raise AssistenteIndisponivel(
            f"OpenRouter respondeu {resposta.status_code}: {resposta.text[:200]}"
        )

    dados = resposta.json()
    if "error" in dados:
        raise AssistenteIndisponivel(str(dados["error"])[:200])

    escolha = (dados.get("choices") or [{}])[0]
    texto = (escolha.get("message") or {}).get("content") or ""
    if not texto.strip():
        raise AssistenteIndisponivel("o modelo devolveu resposta vazia")

    uso = dados.get("usage") or {}
    return Resposta(
        pergunta=pergunta,
        resposta=texto.strip(),
        modelo=dados.get("model") or settings.openrouter_model,
        blocos=blocos,
        recomendacoes=contexto_montado.recomendacoes,
        tokens_entrada=uso.get("prompt_tokens"),
        tokens_saida=uso.get("completion_tokens"),
    )
