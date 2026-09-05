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

from api import vocabulario_esports
from collectors import itad_loja, opgg_mcp, steam_descoberta, steam_loja
from config import get_settings
from db.models import (
    AgendaPartida,
    DimEquipe,
    DimJogo,
    DimJogoSteam,
    DimPartida,
    DimPersonagem,
    FatoAvaliacaoSteam,
    FatoEstatisticaPersonagem,
    FatoPartidaJogador,
    FatoSnapshotJogoSteam,
)
from db.session import session_scope
from etl.transform_itad import MenorHistorico, OfertaItad
from ml.confronto import carregar_relatorio as relatorio_confronto
from ml.confronto import jogos_com_modelo as _jogos_com_modelo_confronto
from ml.sentimento import carregar_metricas as metricas_sentimento

logger = logging.getLogger(__name__)

INSTRUCAO = """\
Você é o assistente de dados do Gaming Analytics, uma plataforma de coleta e \
análise de dados de jogos e esports.

O CONTEXTO abaixo vem em blocos, e cada bloco declara a FONTE dele:

- NOSSO BANCO: dados que a plataforma coletou, mediu e armazenou.
- LOJA DA STEAM: consultada agora, ao vivo, para o jogo citado na pergunta - \
pode ser um jogo que não está no nosso banco.
- STEAMSPY: um terceiro (não é a Steam, não somos nós) consultado agora sobre \
TODO um gênero da Steam - milhares de jogos, não só os do nosso banco. Os \
números dele são estimativas, não medição oficial.
- OP.GG: um terceiro consultado agora sobre League of Legends, TFT e VALORANT - \
jogos que não são da Steam e cujas partidas nós não coletamos. São partidas \
públicas com classificação, do público geral, NÃO do cenário profissional. \
Diga "segundo o OP.GG" e diga que é do público geral.

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
9. Se a pergunta pedir o melhor/pior avaliado "da Steam" ou "do gênero X" (sem \
dizer "do nosso catálogo"/"que vocês monitoram") e houver um bloco fonte \
STEAMSPY, responda com ELE, não com o bloco do nosso banco - é o que cobre a \
Steam inteira, não só os jogos que coletamos. Diga "segundo o SteamSpy" e que \
é sobre o gênero inteiro, não só o nosso catálogo. Se esse bloco disser que \
falta um gênero na pergunta, repita esse pedido em vez de responder com os \
poucos jogos do nosso banco como se fossem "os piores/melhores da Steam".
10. Se a pergunta pedir onde comprar mais barato e o bloco do jogo ao vivo \
trouxer "Melhor preço agora, outras lojas" ou "Menor preço já registrado", \
responda com ESSE número (a loja e o valor), não só o preço da Steam - é \
exatamente o que "mais barato"/"menor valor" pergunta. Se essas linhas não \
existirem no bloco (jogo sem oferta encontrada), diga que não achou preço em \
outra loja agora - não invente uma loja ou um valor.
11. Quando o bloco de recomendação vier da LOJA DA STEAM (título "loja da \
Steam agora"), liste os jogos dele com o número de jogadores agora e o preço, \
e diga que a busca foi feita na loja neste momento e que esses jogos não são \
do nosso banco. NUNCA afirme quantos jogadores cabem numa partida, tamanho de \
grupo ou "suporta squad de N" - a loja não informa isso, e o próprio bloco \
avisa. O que está confirmado é que cada um tem modo online.
12. O bloco "Volumes do banco" lista os jogos de esports que cobrimos e é um MAPA DE CAPACIDADE. NUNCA diga que um jogo listado ali "não está no nosso banco". Ele tem três linhas-chave: (a) para quais jogos existe dado de PARTIDA nosso; (b) para quais existe DESEMPENHO por personagem - winrate, pick rate, meta - e de que fonte (nosso, para Dota; OP.GG, público geral com classificação, para LoL e Valorant); (c) para quais existe GUIA de build. Responda "melhor personagem / meta" só para os jogos da linha (b), sempre dizendo a fonte. Para um jogo fora dela, "o melhor é X" seria opinião com cara de medição - diga que falta essa coleta.
13. Quando houver um bloco "Elenco e desempenho de X - OP.GG", ele responde "melhor campeão/agente" e "meta" desse jogo. Use os números dele, diga "segundo o OP.GG" e que é do público geral com classificação, NÃO do cenário profissional. Se a pergunta for sobre o meta PROFISSIONAL/competitivo, diga que esse recorte não responde isso.
14. Quando houver um bloco "Guia de build - X", ele responde "como jogar / o que buildar / ordem de subir a habilidade / runas" desse personagem. Liste os itens por fase, a prioridade de habilidade e as runas COMO ESTÃO no bloco. É dado do OP.GG/OpenDota (público geral), não do cenário profissional, e é da última coleta - não é ao vivo.
15. Quando houver um bloco "Modelo de confronto", ele diz para quais jogos existe modelo de previsão ajustado. Se a pergunta pedir previsão de um confronto de um jogo SEM modelo na lista, diga que ainda não há modelo para esse jogo. Se o bloco disser que a acurácia não supera a taxa base, a resposta precisa dizer isso - não venda a previsão como confiável.
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
    #: A capa real da loja. Vem preenchida na descoberta ao vivo (a ficha da
    #: Steam ja traz) e fica `None` no caminho do catalogo, onde a tela monta a
    #: arte pelo `app_id`. Sem ela, jogo novo cai no palpite deterministico de
    #: CDN, que da 404 - eles migraram para um caminho com hash.
    imagem_header: str | None = None


@dataclass
class PontoSerie:
    rotulo: str
    valor: float
    detalhe: str | None = None


@dataclass
class SerieAssistente:
    """Os numeros de um bloco, estruturados - o que permite a tela desenhar
    grafico sem inventar nada.

    Nasce da MESMA consulta que escreve o texto do bloco, nao de reler o texto
    depois: interpretar de volta o que nos mesmos formatamos seria fragil, e
    interpretar a resposta do modelo seria pior ainda. O texto e a serie sao
    duas saidas da mesma linha de SQL.
    """

    chave: str
    titulo: str
    unidade: str
    itens: list[PontoSerie] = field(default_factory=list)


@dataclass
class JogoAoVivo:
    """O jogo identificado por `_bloco_steam_ao_vivo`, com preco de outras
    lojas - pronto pra tela desenhar o banner, esteja o jogo no nosso banco ou
    nao (e a resposta ao pedido "traga tudo mesmo nao estando no snapshot"):
    imagem real (`imagem_header`, vem direto do `appdetails` da Steam) e a
    mesma comparacao de preco que a ficha de um jogo do nosso catalogo mostra
    - so que buscada na hora, via IsThereAnyDeal, para um jogo que pode nunca
    ter passado pelo coletor `itad`.
    """

    app_id: int
    nome: str
    #: A capa (460x215): pequena, mas nitida e sempre presente.
    imagem_header: str | None
    #: A arte de fundo da pagina da loja - grande, mas as vezes ja vem
    #: escurecida/borrada pela propria Valve. Serve de fundo, nao de capa.
    imagem_fundo: str | None
    generos: list[str]
    desenvolvedora: str | None
    preco_atual: float | None
    moeda: str | None
    gratuito: bool
    no_nosso_banco: bool
    ofertas: list[OfertaItad] = field(default_factory=list)
    menor_historico: MenorHistorico | None = None


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
    #: O jogo citado na pergunta, quando `_bloco_steam_ao_vivo` o identificou -
    #: `None` na maioria das perguntas (que nao citam um jogo especifico).
    jogo_ao_vivo: JogoAoVivo | None = None
    #: Os numeros dos blocos usados, estruturados. A tela so desenha grafico
    #: se isto vier preenchido - nunca lendo de volta o texto da resposta.
    series: list[SerieAssistente] = field(default_factory=list)
    tokens_entrada: int | None = None
    tokens_saida: int | None = None


class AssistenteIndisponivel(RuntimeError):
    """Falta chave, ou o provedor recusou a chamada."""


# ---------------------------------------------------------------------------
# Montagem do contexto
# ---------------------------------------------------------------------------


#: A Steam guarda o nome com simbolo de marca colado ("HELLDIVERS™ 2"), que
#: ninguem digita numa pergunta - sem remover isso, o nome achado na loja
#: nunca bate com o texto de quem perguntou.
_SIMBOLOS_MARCA = str.maketrans("", "", "™®©")


def _normalizar(texto: str) -> str:
    """Minuscula, sem acento e sem simbolo de marca - para casar 'herói' com
    'heroi', e "HELLDIVERS™ 2" com "helldivers 2".

    O simbolo de marca sai ANTES do NFKD de proposito: "™" tem decomposicao
    de compatibilidade pra "TM" (duas letras!), entao normalizar primeiro e
    so tirar "™"/"®"/"©" depois nunca acha o simbolo - ele ja virou texto.
    """
    sem_marca = texto.translate(_SIMBOLOS_MARCA)
    sem_acento = unicodedata.normalize("NFKD", sem_marca.lower())
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

    # O filtro tira a linha da ultima coleta quando nao ha coleta nenhuma; a
    # cobertura entra depois dele para poder ter linha em branco de separacao.
    corpo = [linha for linha in linhas if linha]
    corpo.extend(["", *_linhas_cobertura(sessao)])

    return Bloco("geral", "Volumes do banco", "\n".join(corpo).strip())


def _linhas_cobertura(sessao) -> list[str]:
    """Que jogos de esports a plataforma cobre, e com que profundidade.

    Existe por causa de uma resposta errada, nao por completude: perguntado
    sobre Valorant, o assistente respondia "Valorant nao esta no nosso banco" e
    caia no conhecimento geral. Era falso - VALORANT esta em `dim_jogo` com 87
    equipes e 87 confrontos na agenda, vindos da Liquipedia. O modelo so nao
    tinha como saber: nenhum bloco falava dos outros jogos, e o unico bloco de
    personagem consultava herois de Dota.

    As tres ultimas linhas sao um mapa de capacidade: separam "temos o jogo" de
    "temos partida", "temos estatistica por personagem" e "temos modelo de
    previsao". Sem elas, ver "VALORANT: 29 agentes" faria o modelo achar que da
    pra ranquear agente sem saber de onde sai o numero - ou negar que da, agora
    que sai (do OP.GG, em `fato_estatistica_personagem`).
    """
    contagens = sessao.execute(
        select(
            DimJogo.codigo,
            DimJogo.nome,
            select(func.count())
            .select_from(DimEquipe)
            .where(DimEquipe.id_jogo == DimJogo.id_jogo)
            .scalar_subquery(),
            select(func.count())
            .select_from(AgendaPartida)
            .where(AgendaPartida.id_jogo == DimJogo.id_jogo)
            .scalar_subquery(),
            select(func.count())
            .select_from(DimPartida)
            .where(DimPartida.id_jogo == DimJogo.id_jogo)
            .scalar_subquery(),
            select(func.count())
            .select_from(DimPersonagem)
            .where(DimPersonagem.id_jogo == DimJogo.id_jogo)
            .scalar_subquery(),
        ).order_by(DimJogo.nome)
    ).all()

    cobertos = [linha for linha in contagens if any(linha[2:])]
    if not cobertos:
        return []

    # Jogos com estatistica agregada por personagem (OP.GG) e com guia de build.
    com_estatistica = set(
        sessao.scalars(
            select(DimJogo.codigo)
            .join(DimPersonagem, DimPersonagem.id_jogo == DimJogo.id_jogo)
            .join(
                FatoEstatisticaPersonagem,
                FatoEstatisticaPersonagem.id_personagem
                == DimPersonagem.id_personagem,
            )
            .distinct()
        )
    )
    com_guia = set(
        sessao.scalars(
            select(DimJogo.codigo)
            .join(DimPersonagem, DimPersonagem.id_jogo == DimJogo.id_jogo)
            .where(DimPersonagem.metadados.has_key("guia"))
            .distinct()
        )
    )
    com_modelo = set(_jogos_com_modelo_confronto())

    linhas = [
        "Jogos de esports no nosso banco (equipes e agenda vem da Liquipedia):"
    ]
    com_partida: list[str] = []
    com_desempenho: list[str] = []
    com_guia_nomes: list[str] = []
    for codigo, nome, equipes, agenda, partidas, personagens in cobertos:
        partes = []
        if equipes:
            partes.append(f"{equipes} equipes")
        if agenda:
            partes.append(f"{agenda} confrontos na agenda")
        if partidas:
            partes.append(f"{partidas} partidas com dado de jogador")
            com_partida.append(nome)
        if personagens:
            partes.append(f"{personagens} personagens/agentes")
        if codigo in com_estatistica:
            partes.append("estatistica por personagem do OP.GG")
        if codigo in com_guia:
            partes.append("guia de build (itens, ordem de habilidade)")
            com_guia_nomes.append(nome)
        if codigo in com_modelo:
            partes.append("modelo de previsao de confronto ajustado")
        if partidas or codigo in com_estatistica:
            com_desempenho.append(nome)
        linhas.append(f"- {nome}: {', '.join(partes)}")

    linhas.append(
        "Dado de PARTIDA nosso (quem jogou, com qual personagem, quem venceu) "
        f"existe so para: {', '.join(com_partida) or 'nenhum jogo'}."
    )
    linhas.append(
        "DESEMPENHO por personagem (winrate, pick rate, meta) tem resposta com "
        f"dado para: {', '.join(com_desempenho) or 'nenhum jogo'} - para Dota e "
        "medicao nossa das partidas; para LoL e Valorant e o OP.GG (publico "
        "geral com classificacao, NAO cenario profissional). Nos demais jogos "
        "da pra falar de equipes, agenda e elenco, nao de meta."
    )
    linhas.append(
        "GUIA de como jogar um personagem (build de item, ordem de subir a "
        f"habilidade, runas): {', '.join(com_guia_nomes) or 'nenhum jogo'} - "
        "a tela de detalhe do personagem (/herois) mostra a ficha completa."
    )
    return linhas


def _bloco_steam(sessao) -> tuple[Bloco, SerieAssistente]:
    recentes = (
        select(FatoSnapshotJogoSteam)
        .distinct(FatoSnapshotJogoSteam.app_id)
        .order_by(
            FatoSnapshotJogoSteam.app_id, desc(FatoSnapshotJogoSteam.janela_coleta)
        )
        .subquery()
    )

    linhas = []
    pontos: list[PontoSerie] = []
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
        if jogadores:
            pontos.append(
                PontoSerie(
                    rotulo=nome,
                    valor=float(jogadores),
                    detalhe=f"{nota}% positivas" if nota is not None else None,
                )
            )

    bloco = Bloco(
        "steam",
        "Catalogo da Steam (ultimo snapshot de cada jogo)",
        "\n".join(linhas) or "Nenhum jogo coletado.",
    )
    serie = SerieAssistente(
        chave="steam",
        titulo="Jogadores simultâneos agora",
        unidade="jogadores",
        itens=pontos[:8],
    )
    return bloco, serie


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

    "Qual jogo de ação tem a PIOR avaliação" cita genero mas NAO pede
    recomendacao nenhuma - pede o extremo oposto, e quem responde por isso e
    `_bloco_extremo_avaliacao` (que busca em toda a Steam, nao so aqui). Sem
    esta checagem essa pergunta acionava os dois blocos e a tela mostrava
    cartao de jogo bom (Hades, Terraria...) do lado de uma resposta sobre o
    pior jogo - dois blocos discordando na mesma tela.
    """
    if _extremo_avaliacao_pedido(pergunta) is not None:
        return None, []

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


# ---------------------------------------------------------------------------
# Elenco de personagens de um jogo sem dado de partida
# ---------------------------------------------------------------------------


def _bloco_elenco(pergunta: str, sessao) -> tuple[Bloco | None, SerieAssistente | None]:
    """O elenco do jogo que a pergunta cita, quando o elenco e tudo que temos.

    Nasce da pergunta "qual o melhor agente do Valorant no meta atual?", que o
    assistente respondia com "Valorant nao esta no nosso banco" - falso - e
    depois com o conhecimento geral do modelo.

    O bloco so entra para jogo SEM partida coletada. Para Dota, que tem 115
    partidas, quem responde e `_bloco_herois`, com winrate medido; listar o
    elenco ali seria repetir pior o que ja existe.

    E ele carrega a recusa junto com o dado, de proposito. Elenco responde
    "quem existe e de que funcao"; nao responde "quem esta forte agora", porque
    isso exige taxa de escolha e de vitoria, que so sai de partida coletada.
    Sem essa frase no contexto, ver 29 agentes listados convida o modelo a
    ordenar os oito duelistas por conta propria.
    """
    normalizada = _normalizar(pergunta)
    tokens = re.findall(r"[a-z0-9]+", normalizada)
    trechos = {
        " ".join(tokens[i:j])
        for i in range(len(tokens))
        for j in range(i + 1, min(i + 4, len(tokens)) + 1)
    }

    candidatos = sessao.execute(
        select(
            DimJogo.id_jogo,
            DimJogo.codigo,
            DimJogo.nome,
            select(func.count())
            .select_from(DimPartida)
            .where(DimPartida.id_jogo == DimJogo.id_jogo)
            .scalar_subquery(),
        )
    ).all()

    alvo = None
    for id_jogo, codigo, nome, partidas in candidatos:
        if partidas:
            continue
        if _normalizar(nome) in trechos:
            alvo = (id_jogo, codigo, nome)
            break
    if alvo is None:
        return None, None

    id_jogo, codigo_jogo, nome_jogo = alvo
    elenco = sessao.execute(
        select(DimPersonagem.nome, DimPersonagem.papel, DimPersonagem.id_externo)
        .where(DimPersonagem.id_jogo == id_jogo)
        .order_by(DimPersonagem.papel, DimPersonagem.nome)
    ).all()
    if not elenco:
        return None, None

    desempenho = _desempenho_externo(sessao, codigo_jogo)
    if desempenho:
        return _elenco_com_desempenho(nome_jogo, codigo_jogo, elenco, desempenho)
    return _elenco_sem_desempenho(nome_jogo, elenco), None


def _desempenho_externo(sessao, codigo_jogo: str) -> dict[str, dict[str, Any]]:
    """Desempenho agregado por personagem, do ULTIMO snapshot ARMAZENADO de
    `fato_estatistica_personagem` (LoL e Valorant, fonte OP.GG).

    Le o banco, nao chama o OP.GG: quem fala com o servidor MCP e o coletor,
    numa rodada agendada. O assistente responde uma pergunta com o que ja foi
    coletado - uma fonte externa lenta no caminho da pergunta seria o defeito
    que a arquitetura deste modulo evita.

    Indexado por `id_externo` em minusculo (o uuid do agente, o id numerico do
    campeao) - a mesma chave que casa `dim_personagem` com a fonte sem
    heuristica de nome. Vazio quando o jogo nao tem essa coleta, e ai o bloco
    volta a ser so o elenco.
    """
    janela = sessao.scalar(
        select(func.max(FatoEstatisticaPersonagem.janela_coleta))
        .select_from(FatoEstatisticaPersonagem)
        .join(
            DimPersonagem,
            DimPersonagem.id_personagem == FatoEstatisticaPersonagem.id_personagem,
        )
        .join(DimJogo, DimJogo.id_jogo == DimPersonagem.id_jogo)
        .where(DimJogo.codigo == codigo_jogo)
    )
    if janela is None:
        return {}

    linhas = sessao.execute(
        select(
            DimPersonagem.id_externo,
            DimPersonagem.nome,
            FatoEstatisticaPersonagem.partidas,
            FatoEstatisticaPersonagem.vitorias,
            FatoEstatisticaPersonagem.metricas,
        )
        .join(
            DimPersonagem,
            DimPersonagem.id_personagem == FatoEstatisticaPersonagem.id_personagem,
        )
        .join(DimJogo, DimJogo.id_jogo == DimPersonagem.id_jogo)
        .where(
            DimJogo.codigo == codigo_jogo,
            FatoEstatisticaPersonagem.janela_coleta == janela,
            FatoEstatisticaPersonagem.mapa == "",  # `""` = o agregado geral
        )
    ).all()

    saida: dict[str, dict[str, Any]] = {}
    for id_externo, nome, partidas, vitorias, metricas in linhas:
        p = int(partidas or 0)
        v = int(vitorias or 0)
        saida[(id_externo or "").lower()] = {
            "nome": nome,
            "partidas": p,
            "vitorias": v,
            "winrate": round(100 * v / p, 1) if p else 0.0,
            "metricas": metricas or {},
        }
    return saida


def _elenco_sem_desempenho(nome_jogo: str, elenco: list[Any]) -> Bloco:
    """Só quem existe e de que função - e a recusa explicita do resto."""
    por_papel: dict[str, list[str]] = {}
    for nome_personagem, papel, _ in elenco:
        por_papel.setdefault(papel or "sem funcao declarada", []).append(nome_personagem)

    linhas = [f"Elenco de {nome_jogo} no nosso banco, por funcao:"]
    for papel, nomes in sorted(por_papel.items()):
        linhas.append(f"- {papel} ({len(nomes)}): {', '.join(nomes)}")
    linhas.append(
        f"NAO temos nenhuma partida de {nome_jogo} coletada e nao ha fonte "
        "externa de desempenho para este jogo agora. Sem isso NAO existe "
        "resposta com dado para 'melhor personagem', 'mais forte' ou 'meta "
        "atual'. Diga isso e diga o que temos (elenco, funcao, equipes, "
        "agenda). Se for falar do meta mesmo assim, use o prefixo 'Fora dos "
        "dados: ' e nao escreva numero nenhum."
    )
    return Bloco("elenco", f"Elenco de {nome_jogo}", "\n".join(linhas))


def _elenco_com_desempenho(
    nome_jogo: str,
    codigo_jogo: str,
    elenco: list[Any],
    desempenho: dict[str, dict[str, Any]],
) -> tuple[Bloco, SerieAssistente | None]:
    """Elenco + desempenho por personagem, do snapshot que coletamos do OP.GG.

    O casamento e por `id_externo`: o OP.GG devolve o mesmo uuid de agente que
    a valorant-api.com e o mesmo id de campeao que o Data Dragon - nao ha
    heuristica de nome no meio, o risco de colar a estatistica no personagem
    errado simplesmente nao existe.

    Cada metrica sai com o rotulo do proprio esporte (`vocabulario_esports`):
    "HS% / ADR" para o agente, "Pick% / Ban% / Tier" para o campeao. A ordem e
    por taxa de ESCOLHA - em jogo equilibrado a vitoria varia pouco e ranquear
    por ela poria em primeiro um personagem pouco jogado por meio ponto; taxa
    de escolha e o que a palavra "meta" costuma querer dizer.
    """
    perfil = vocabulario_esports.perfil(codigo_jogo)

    def _pick(dados: dict[str, Any] | None) -> float:
        if not dados:
            return -1.0
        taxa = (dados.get("metricas") or {}).get("pick_rate")
        return float(taxa) if isinstance(taxa, (int, float)) else -1.0

    linhas_ordenadas = sorted(
        (
            (nome, papel, desempenho.get((id_externo or "").lower()))
            for nome, papel, id_externo in elenco
        ),
        key=lambda item: _pick(item[2]),
        reverse=True,
    )

    total_partidas = sum(d["partidas"] for d in desempenho.values())
    colunas = ", ".join(m.rotulo for m in perfil.metricas) or "winrate"
    linhas = [
        f"Desempenho por {perfil.substantivo} de {nome_jogo}, do OP.GG (ultimo "
        f"snapshot que coletamos). Amostra somada: {total_partidas} "
        f"participacoes em partidas publicas com classificacao. "
        f"Metricas: {colunas}. Ordem por taxa de escolha:",
    ]
    pontos: list[PontoSerie] = []
    for nome, papel, dados in linhas_ordenadas:
        if dados is None:
            linhas.append(
                f"- {nome} ({papel or 'sem funcao'}): sem estatistica no OP.GG"
            )
            continue
        metricas = dados["metricas"]
        partes = [f"{dados['winrate']}% de vitorias"]
        for metrica in perfil.metricas:
            valor = metricas.get(metrica.chave)
            if isinstance(valor, (int, float)):
                partes.append(f"{metrica.rotulo} {valor}{metrica.unidade}")
        linhas.append(
            f"- {nome} ({papel or 'sem funcao'}): {', '.join(partes)}, "
            f"em {dados['partidas']} partidas"
        )
        taxa = metricas.get("pick_rate")
        if isinstance(taxa, (int, float)):
            pontos.append(
                PontoSerie(
                    rotulo=nome,
                    valor=float(taxa),
                    detalhe=f"{dados['winrate']}% de vitorias",
                )
            )

    linhas.append(
        "Estes numeros sao do OP.GG, um terceiro - nao sao medicao nossa e nao "
        "sao do cenario profissional: sao partidas publicas com classificacao. "
        "Diga 'segundo o OP.GG' e diga que e do publico geral. Se a pergunta "
        "for sobre o meta PROFISSIONAL, avise que este recorte nao responde isso."
    )
    if codigo_jogo == "valorant":
        linhas.append(
            "As taxas de vitoria de Valorant ficam quase todas entre 48% e 52% - "
            "meio ponto de diferenca NAO faz um agente 'melhor'. Se a pergunta "
            "pedir o melhor, responda pelo conjunto (escolha + vitoria) e diga "
            "que a diferenca de vitoria e pequena."
        )

    serie = SerieAssistente(
        chave="elenco",
        titulo=f"Taxa de escolha — {nome_jogo} (OP.GG)",
        unidade="%",
        itens=pontos[:8],
    )
    return (
        Bloco(
            "elenco",
            f"Elenco e desempenho de {nome_jogo} - OP.GG",
            "\n".join(linhas),
            fonte="opgg",
        ),
        serie,
    )


# ---------------------------------------------------------------------------
# Descoberta na loja: jogos por caracteristica, fora do nosso catalogo
# ---------------------------------------------------------------------------

#: Palavras que dizem "quero jogar com outras pessoas".
#:
#: Separadas em tres grupos porque elas escolhem FILTRO diferente na busca da
#: loja: quem pede cooperativo nao quer PvP e vice-versa. As genericas ligam os
#: dois - "jogar com amigos" nao diz se e um contra o outro ou lado a lado.
TERMOS_COOPERATIVO = (
    "coop", "co op", "cooperativo", "cooperativa", "pve", "juntos",
)
TERMOS_COMPETITIVO = (
    "pvp", "competitivo", "ranqueado", "contra outros", "contra outras pessoas",
)
TERMOS_MULTIJOGADOR = (
    "amigo", "amigos", "galera", "turma", "squad", "grupo", "equipe", "time",
    "multiplayer", "multijogador", "online", "duo", "trio", "pessoas",
)


def _modo_multijogador(pergunta: str) -> tuple[bool, bool] | None:
    """`(cooperativo, competitivo)` que a pergunta pede, ou `None` se ela nao
    fala de jogar acompanhado."""
    normalizada = _normalizar(pergunta)
    tokens = set(re.findall(r"[a-z0-9]+", normalizada))

    def cita(termos: tuple[str, ...]) -> bool:
        return any(
            (termo in normalizada) if " " in termo else (termo in tokens)
            for termo in termos
        )

    cooperativo = cita(TERMOS_COOPERATIVO)
    competitivo = cita(TERMOS_COMPETITIVO)
    if cooperativo or competitivo:
        return cooperativo, competitivo
    if cita(TERMOS_MULTIJOGADOR):
        # Sem dizer como, vale os dois - a lista fica mais larga, e e o
        # comportamento certo: "com amigos" cabe em Rainbow Six e em Deep Rock.
        return True, True
    return None


def _bloco_descoberta(
    pergunta: str,
) -> tuple[Bloco | None, list[JogoRecomendado], SerieAssistente | None]:
    """Recomendacao por CARACTERISTICA, buscada na loja da Steam na hora.

    Responde a classe de pergunta que o catalogo proprio nunca vai responder:
    "jogos de tiro FPS pra jogar com cinco amigos". Nosso banco guarda os
    generos grossos da Steam e nenhuma categoria - nao ha coluna que diga "tem
    PvP online" -, entao a pergunta caia no bloco de "melhor avaliado do
    catalogo", que responde outra coisa.

    Roda quando a pergunta cita uma TAG que a Steam reconhece (a lista oficial
    de tags e quem diz que "FPS" existe e vale 1663) e fala de jogar
    acompanhado. As duas condicoes juntas, porque cada uma sozinha erraria:
    so a tag pegaria "melhor jogo de FPS" (que e sobre nota, nao sobre grupo),
    e so o modo pegaria "meus amigos jogam o que?" - sem genero pra filtrar.

    O que este bloco DECLARA nao saber e tao importante quanto o que ele traz:
    a loja nao expoe tamanho de grupo. "Cinco pessoas" nao e consultavel, e
    dizer isso no contexto e o que impede o modelo de responder "suporta
    squads de 5" com cara de dado.
    """
    modo = _modo_multijogador(pergunta)
    if modo is None:
        return None, [], None

    tag = steam_descoberta.resolver_tag(pergunta)
    if tag is None:
        return None, [], None

    tag_id, tag_nome = tag
    cooperativo, competitivo = modo
    achados = steam_descoberta.multijogador_por_tag(
        tag_id, cooperativo=cooperativo, competitivo=competitivo
    )

    filtro = (
        "cooperativo online" if cooperativo and not competitivo
        else "PvP online" if competitivo and not cooperativo
        else "PvP ou cooperativo online"
    )
    rotulo = f"{tag_nome}, {filtro}"

    if not achados:
        return (
            Bloco(
                "descoberta",
                f"Recomendação ({rotulo})",
                f"A busca na loja da Steam por '{tag_nome}' com {filtro} não "
                "devolveu nenhum jogo agora. Diga que a busca não trouxe "
                "resultado - não substitua por jogos de memória.",
                fonte="steam",
            ),
            [],
            None,
        )

    linhas = [
        f"Jogos da loja da Steam com a tag '{tag_nome}' e {filtro}, consultados "
        "AGORA (não são do nosso banco). Ordem: quem tem mais gente jogando "
        "neste instante. Recomende só entre estes:",
    ]
    recomendados: list[JogoRecomendado] = []
    pontos: list[PontoSerie] = []

    for jogo in achados:
        preco_texto = (
            "Gratuito"
            if jogo["gratuito"]
            else f"{jogo['moeda'] or ''} {jogo['preco']}".strip()
            if jogo["preco"] is not None
            else "sem preço na região"
        )
        linhas.append(
            f"- {jogo['nome']}: {jogo['jogadores_agora'] or 0} jogadores agora, "
            f"{preco_texto}, modos {', '.join(jogo['categorias']) or '-'}, "
            f"gêneros {', '.join(jogo['generos']) or '-'}"
        )
        recomendados.append(
            JogoRecomendado(
                app_id=jogo["app_id"],
                nome=jogo["nome"],
                generos=jogo["generos"],
                # A busca por caracteristica nao passa pelas avaliacoes: pedir a
                # nota de cada candidato dobraria as chamadas por pergunta, e o
                # criterio aqui e "tem gente jogando", nao "e bem avaliado".
                nota_avaliacoes=None,
                jogadores_simultaneos=jogo["jogadores_agora"],
                preco=jogo["preco"],
                moeda=jogo["moeda"],
                gratuito=jogo["gratuito"],
                imagem_header=jogo["imagem_header"],
            )
        )
        if jogo["jogadores_agora"]:
            pontos.append(
                PontoSerie(
                    rotulo=jogo["nome"],
                    valor=float(jogo["jogadores_agora"]),
                    detalhe="Gratuito" if jogo["gratuito"] else preco_texto,
                )
            )

    linhas.append(
        "A loja NÃO informa tamanho de grupo nem quantos jogadores cabem numa "
        "partida. O que está confirmado é que cada um destes tem modo online "
        "(PvP ou cooperativo) na categoria da própria Steam. Não afirme que "
        "algum suporta exatamente 5 jogadores - isso não está nos dados."
    )

    serie = SerieAssistente(
        chave="descoberta",
        titulo=f"Jogando agora — {tag_nome}",
        unidade="jogadores",
        itens=pontos[:8],
    )

    return (
        Bloco(
            "descoberta",
            f"Recomendação ({rotulo}) - loja da Steam agora",
            "\n".join(linhas),
            fonte="steam",
        ),
        recomendados,
        serie,
    )


# ---------------------------------------------------------------------------
# Extremo de avaliacao em TODA a Steam (SteamSpy, nao so o nosso catalogo)
# ---------------------------------------------------------------------------

#: "melhor"/"pior" avaliado - o rotulo tambem e o que entra no texto do bloco.
GATILHOS_EXTREMO_AVALIACAO: dict[str, tuple[str, ...]] = {
    "pior": ("pior avaliacao", "pior avaliado", "pior nota", "mais mal avaliado",
             "menos aprovado", "mais reprovado"),
    "melhor": ("melhor avaliacao", "melhor avaliado", "melhor nota",
               "mais bem avaliado", "mais aprovado"),
}


def _extremo_avaliacao_pedido(pergunta: str) -> str | None:
    """`"pior"`, `"melhor"` ou `None` - qual extremo a pergunta pede, se algum."""
    normalizada = _normalizar(pergunta)
    for rotulo, termos in GATILHOS_EXTREMO_AVALIACAO.items():
        if any(_normalizar(termo) in normalizada for termo in termos):
            return rotulo
    return None


def _bloco_extremo_avaliacao(pergunta: str) -> Bloco | None:
    """O melhor/pior avaliado de um genero, em TODA a Steam - nao so o nosso banco.

    Devolve `None` quando a pergunta nao pede extremo nenhum (o caso comum).
    Quando pede mas SEM genero, o bloco ainda entra - so que pedindo o genero
    de volta, em vez de silenciosamente responder com os poucos jogos do
    nosso catalogo como se fossem "os piores/melhores da Steam" (o problema
    relatado: um catalogo de 20 e poucos jogos nao tem como responder por
    toda a loja, e a resposta antiga nao deixava isso claro o bastante).
    """
    extremo = _extremo_avaliacao_pedido(pergunta)
    if extremo is None:
        return None

    genero = _genero_pedido(pergunta)
    if genero is None:
        return Bloco(
            "extremo_avaliacao",
            "Melhor/pior avaliado em toda a Steam",
            "Falta o gênero na pergunta. Buscar isso em TODA a Steam (não só "
            "o nosso catálogo de 20 e poucos jogos) só é possível por gênero "
            "- ação, aventura, rpg, estratégia, indie, simulação, "
            "multijogador, acesso antecipado ou gratuito. Peça à pessoa para "
            "citar um gênero; não responda com o pior/melhor do nosso "
            "catálogo como se fosse resposta sobre a Steam inteira.",
        )

    achado = steam_loja.extremo_avaliacao_por_genero(genero, pior=(extremo == "pior"))
    if achado is None:
        return Bloco(
            "extremo_avaliacao",
            f"{'Pior' if extremo == 'pior' else 'Melhor'} avaliado de {genero} (SteamSpy)",
            "A consulta ao SteamSpy falhou ou não achou nenhum jogo do gênero "
            f"{genero} com avaliações suficientes agora. Diga que a consulta "
            "à Steam inteira falhou - não substitua pelo nosso catálogo sem "
            "avisar que é uma base muito menor.",
            fonte="steam",
        )

    proporcao = round(achado["proporcao_positiva"] * 100, 1)
    linhas = [
        f"FONTE: SteamSpy, consultado agora - estimativa de terceiro sobre "
        f"avaliações públicas de TODO o gênero {genero} na Steam (milhares de "
        "jogos, não só os do nosso catálogo).",
        f"Nome: {achado['nome']}",
        f"AppID: {achado['app_id']}",
        f"Avaliações positivas: {proporcao}% "
        f"({achado['positivas']} positivas, {achado['negativas']} negativas, "
        f"{achado['total_avaliacoes']} avaliações no total)",
        f"Donos estimados: {achado['owners']}",
    ]

    return Bloco(
        "extremo_avaliacao",
        f"{'Pior' if extremo == 'pior' else 'Melhor'} avaliado de {genero}, "
        "em toda a Steam (SteamSpy)",
        "\n".join(linhas),
        fonte="steam",
    )


def _bloco_partidas(sessao) -> tuple[Bloco, None]:
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
    bloco = Bloco(
        "partidas", "Dominio de partidas (Dota 2)", "\n".join(l for l in linhas if l)
    )
    # Sem serie: o bloco e um resumo (total, media, torneios), nao um ranking
    # comparavel - grafico aqui nao diria nada. A lista de ligas ate seria
    # plotavel, mas "quantas partidas por torneio" nunca e a pergunta que traz
    # alguem a este bloco.
    return bloco, None


def _bloco_herois(sessao) -> tuple[Bloco, SerieAssistente]:
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

    bloco = Bloco(
        "herois",
        "Herois com 5+ partidas (melhores e piores winrates)",
        formatar(linhas[:8]) + "\n...\n" + formatar(linhas[-8:])
        if len(linhas) > 16
        else formatar(linhas),
    )
    serie = SerieAssistente(
        chave="herois",
        titulo="Winrate por herói (5+ partidas)",
        unidade="%",
        itens=[
            PontoSerie(
                rotulo=nome,
                valor=round(float(winrate), 1),
                detalhe=f"{n} partidas",
            )
            for nome, n, winrate in linhas[:8]
        ],
    )
    return bloco, serie


def _jogo_citado(pergunta: str, sessao) -> tuple[str, str] | None:
    """`(codigo, nome)` do jogo de `dim_jogo` cujo nome aparece na pergunta.

    O casamento e por n-grama (o mesmo de `_bloco_elenco`), do nome mais longo
    para o mais curto - "League of Legends" ganha de "League" se os dois
    existissem. Serve aos blocos que precisam saber "de que jogo e a pergunta"
    sem repetir a deteccao.
    """
    normalizada = _normalizar(pergunta)
    jogos = sessao.execute(select(DimJogo.codigo, DimJogo.nome)).all()
    achados = [
        (codigo, nome)
        for codigo, nome in jogos
        if _normalizar(nome) in normalizada
    ]
    if not achados:
        return None
    return max(achados, key=lambda par: len(par[1]))


def _bloco_modelos(pergunta: str, sessao) -> Bloco:
    """As metricas do modelo de previsao de confronto entre equipes.

    Ha UM modelo por jogo (`ml/confronto`, um arquivo por jogo). O bloco
    responde pelo jogo citado na pergunta; sem jogo citado, pelo Dota, que e o
    de historico mais fundo. E lista para quais jogos existe modelo - a
    pergunta "voces preveem CS?" precisa dessa resposta.

    A validacao vem inteira, inclusive quando e ruim: se a acuracia nao supera
    a taxa base, o bloco manda dizer isso. Vender confianca que o numero nao
    sustenta e o oposto do proposito da plataforma.
    """
    disponiveis = _jogos_com_modelo_confronto()
    if not disponiveis:
        return Bloco(
            "modelos",
            "Modelo de confronto",
            "Nenhum modelo de confronto ajustado ainda "
            "(rode `python cli.py train-confronto`).",
        )

    citado = _jogo_citado(pergunta, sessao)
    nomes = {codigo: nome for codigo, nome in sessao.execute(select(DimJogo.codigo, DimJogo.nome))}
    if citado and citado[0] in disponiveis:
        alvo = citado[0]
    elif "dota2" in disponiveis:
        alvo = "dota2"
    else:
        alvo = disponiveis[0]
    nome_alvo = nomes.get(alvo, alvo)

    relatorio = relatorio_confronto(alvo)
    if relatorio is None:
        return Bloco(
            "modelos",
            "Modelo de confronto",
            f"Nenhum modelo de confronto ajustado para {nome_alvo}.",
        )

    validacao = relatorio.get("validacao") or {}
    lista_jogos = ", ".join(sorted(nomes.get(j, j) for j in disponiveis))
    linhas = [
        f"Modelo de previsao de confronto de {nome_alvo}.",
        f"Existe modelo ajustado para: {lista_jogos}.",
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


#: Palavras que dizem "quero saber COMO JOGAR o personagem", nao "como ele
#: esta". Guia responde build e ordem de skill; desempenho responde meta.
GATILHOS_GUIA = (
    "build", "buildar", "buildo", "item", "itens", "itemizacao", "montar",
    "ordem", "upar", "subir habilidade", "skill order", "runa", "runas",
    "feitico", "feiticos", "como jogar", "como jogo", "como usar", "guia",
)


def _bloco_guia(pergunta: str, sessao) -> Bloco | None:
    """A build do meta e a ordem de habilidade do personagem que a pergunta cita.

    So entra quando a pergunta pede COMO JOGAR (build, item, ordem de skill,
    runa) E nomeia um personagem que tem guia coletado. Sem os dois, o bloco
    fica de fora - "qual o melhor campeao?" nao e pergunta de build.

    A fonte e o OP.GG (LoL) ou a OpenDota (Dota), pela coleta agendada, gravada
    em `dim_personagem.metadados`. Nao ha chamada externa aqui.
    """
    normalizada = _normalizar(pergunta)
    if not any(_normalizar(termo) in normalizada for termo in GATILHOS_GUIA):
        return None

    candidatos = sessao.execute(
        select(DimPersonagem.nome, DimJogo.nome, DimPersonagem.metadados)
        .join(DimJogo, DimJogo.id_jogo == DimPersonagem.id_jogo)
        .where(DimPersonagem.metadados.has_key("guia"))
    ).all()

    alvo = None
    for nome_p, nome_jogo, metadados in candidatos:
        if _normalizar(nome_p) in normalizada:
            alvo = (nome_p, nome_jogo, (metadados or {}).get("guia") or {})
            break
    if alvo is None or not alvo[2]:
        return None

    nome_p, nome_jogo, guia = alvo
    fonte = guia.get("fonte") or "OP.GG"
    rota = guia.get("rota")
    linhas = [
        f"Guia de {nome_p} ({nome_jogo}), do {fonte}"
        + (f", rota {rota}" if rota else "")
        + (f" - coleta de {guia['atualizado_em']}." if guia.get("atualizado_em") else "."),
    ]

    for grupo in guia.get("grupos") or []:
        itens = ", ".join(i.get("nome", "") for i in grupo.get("itens") or [] if i.get("nome"))
        if itens:
            nota = f" ({grupo['nota']})" if grupo.get("nota") else ""
            linhas.append(f"{grupo.get('titulo', 'Itens')}: {itens}{nota}")

    ordem = guia.get("ordem_habilidades") or []
    prioridade = guia.get("prioridade_habilidades") or []
    if prioridade:
        linhas.append(f"Prioridade de subir: {' > '.join(prioridade)}.")
    if ordem:
        linhas.append("Ordem por nivel: " + " ".join(ordem) + ".")
    if guia.get("nota_habilidades"):
        linhas.append(guia["nota_habilidades"])

    feiticos = guia.get("feiticos") or []
    if feiticos:
        linhas.append("Feiticos de invocador: " + ", ".join(feiticos) + ".")
    for chave_runa, rotulo in (("runa_primaria", "Runa primaria"), ("runa_secundaria", "Runa secundaria")):
        runa = guia.get(chave_runa)
        if runa and runa.get("escolhas"):
            linhas.append(f"{rotulo} ({runa.get('pagina', '?')}): " + ", ".join(runa["escolhas"]) + ".")

    linhas.append(
        f"Estes numeros e escolhas sao do {fonte}, do publico geral com "
        "classificacao - nao e cenario profissional. A tela /herois mostra a "
        "ficha completa, com icone e video das habilidades."
    )
    return Bloco("guia", f"Guia de build - {nome_p}", "\n".join(linhas), fonte="opgg")


def _bloco_sentimento(sessao) -> tuple[Bloco, SerieAssistente]:
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

    bloco = Bloco(
        "sentimento",
        "Sentimento das avaliacoes",
        "\n".join(linhas) or "Nenhuma avaliacao coletada.",
    )
    serie = SerieAssistente(
        chave="sentimento",
        titulo="Avaliações positivas por jogo (coletadas)",
        unidade="%",
        itens=[
            PontoSerie(
                rotulo=nome,
                valor=round(100 * float(pos or 0) / total, 1),
                detalhe=f"{total} avaliações",
            )
            for nome, total, pos in por_jogo[:8]
        ],
    )
    return bloco, serie


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
    pelo pela pelos pelas menor maior barata baratas custo custar
    encontro encontra encontrar acha achar comprar compra comprando compro
    posso consigo consegue vende vender vendendo desconto promocao
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


#: Numeral romano -> arabico, so I-X (nenhum jogo de sequencia comum passa
#: disso). Aplicado token a token, nunca como troca de substring solta -
#: "vix" nao pode virar "9x".
_ROMANO_PARA_ARABICO = {
    "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5",
    "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10",
}


def _formas_comparaveis(texto: str) -> set[str]:
    """As formas de `texto` que valem como "o mesmo nome", so escrito diferente.

    Duas folgas, e as duas sao FORMATACAO, nunca ambiguidade de jogo:

    * **Pontuacao e espaco somem.** O titulo oficial tem pontuacao que ninguem
      digita numa pergunta: "Call of Duty®: Modern Warfare® III" (dois-pontos),
      "Marvel's Spider-Man" (apostrofo e hifen), "S.T.A.L.K.E.R. 2" (pontos).
      Comparar so o alfanumerico resolve os tres de uma vez.
    * **Numeral romano vira arabico, e vice-versa.** O mesmo jogo e
      "Helldivers 2" na Steam e "Helldivers II" na boca do mundo - e ao
      contrario em "Diablo IV"/"Diablo 4".

    O que NAO afrouxa: o nome inteiro continua tendo que aparecer, em ordem.
    """
    tokens = re.findall(r"[a-z0-9]+", texto)
    arabico_para_romano = {v: k for k, v in _ROMANO_PARA_ARABICO.items()}

    formas = {"".join(tokens)}
    for mapa in (_ROMANO_PARA_ARABICO, arabico_para_romano):
        formas.add("".join(mapa.get(token, token) for token in tokens))
    return formas


def _confirma_nome(nome: str, pergunta: str) -> bool:
    """O nome achado na loja precisa estar DENTRO da pergunta, nao parecer com ela.

    Contencao deliberada, e a mesma do casamento de times em
    `etl/load_liquipedia.py`: buscar "mais caros" na loja devolve algum app, e
    aceitar esse app produziria uma resposta confiante sobre o jogo errado -
    que e pior que nao responder. Por isso a exigencia e de conter o nome
    inteiro, contiguo - as unicas folgas sao as de escrita listadas em
    `_formas_comparaveis`.
    """
    alvo = _normalizar(nome)
    if len(re.sub(r"[^a-z0-9]+", "", alvo)) < MINIMO_DO_TERMO:
        return False

    pergunta_comparavel = "".join(re.findall(r"[a-z0-9]+", _normalizar(pergunta)))
    if not any(forma in pergunta_comparavel for forma in _formas_comparaveis(alvo)):
        return False

    # Um app chamado "Mais" casaria com quase toda pergunta em portugues.
    return any(t not in PALAVRAS_VAZIAS for t in re.findall(r"[a-z0-9]+", alvo))


def _bloco_steam_ao_vivo(
    pergunta: str, sessao
) -> tuple[Bloco | None, JogoAoVivo | None]:
    """Consulta a loja da Steam (e o ITAD) sobre o jogo citado na pergunta.

    Devolve `(None, None)` sempre que a identificacao nao for segura - sem
    termo, sem resultado, ou com resultado que nao bate com a pergunta. O
    assistente entao se comporta como antes, respondendo pelo banco: perder o
    bloco custa uma resposta mais pobre, enquanto um bloco errado custa uma
    resposta falsa.

    O segundo item devolvido (`JogoAoVivo`) e o que a tela usa pra desenhar o
    banner com imagem e a comparacao de preco - existe separado do texto do
    bloco pelo mesmo motivo de `JogoRecomendado`: a tela nunca deveria
    precisar adivinhar de qual jogo (e quais ofertas) o texto do modelo fala.
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
        return None, None

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
    gratuito = bool(dados.get("is_free"))
    generos = [
        str(g["description"]) for g in (dados.get("genres") or []) if isinstance(g, dict)
    ]

    linhas = [
        "FONTE: loja da Steam, consultada agora (dado externo, nao medido por nos).",
        procedencia,
        "",
        f"Nome: {nome}",
        f"AppID: {app_id}",
        f"Desenvolvedora: {', '.join(dados.get('developers') or [])}",
        f"Generos: {', '.join(generos)}",
        f"Lancamento: {lancamento.get('date', '')}",
        f"Gratuito: {'sim' if gratuito else 'nao'}",
        f"Preco na loja da Steam: {preco.get('final_formatted', '')}",
        f"Avaliacoes na Steam (total): {total if total is not None else ''}",
        f"Avaliacoes positivas: {positivas if positivas is not None else ''}",
        f"Classificacao da Steam: {resumo.get('review_score_desc', '')}",
    ]

    # Preco noutras lojas: SEMPRE tentado, esteja o jogo no nosso banco ou nao
    # - e exatamente o caso que faltava ("onde encontro mais barato" sobre um
    # jogo que nunca passou pelo coletor `itad`).
    ofertas: list[OfertaItad] = []
    menor_historico: MenorHistorico | None = None
    if not gratuito:
        resultado_itad = itad_loja.preco_ao_vivo(app_id)
        if resultado_itad is not None:
            ofertas, menor_historico = resultado_itad
            if ofertas:
                mais_barata = min(ofertas, key=lambda o: o.preco)
                linhas.append(
                    f"Melhor preco agora, outras lojas (IsThereAnyDeal, ao vivo): "
                    f"{mais_barata.loja} por {mais_barata.moeda or ''} {mais_barata.preco}".strip()
                )
                linhas.append(
                    "Todas as ofertas agora: "
                    + "; ".join(
                        f"{o.loja} {o.moeda or ''} {o.preco}".strip() for o in ofertas
                    )
                )
            if menor_historico is not None:
                linhas.append(
                    f"Menor preco ja registrado (IsThereAnyDeal): "
                    f"{menor_historico.moeda or ''} {menor_historico.preco} "
                    f"na {menor_historico.loja or '-'}"
                    + (f" em {menor_historico.data}" if menor_historico.data else "")
                )

    # Linha sem valor e ruido que o modelo tenta interpretar; fora.
    conteudo = "\n".join(l for l in linhas if not l.rstrip().endswith(":"))

    bloco = Bloco(
        chave="steam_ao_vivo",
        titulo=f"{nome} - loja da Steam, ao vivo",
        conteudo=conteudo,
        fonte="steam",
    )

    jogo_ao_vivo = JogoAoVivo(
        app_id=app_id,
        nome=nome,
        # As duas imagens, cada uma pro que ela presta - ver `CartaoJogoAoVivo`.
        # `header_image` e a capa nitida: pequena (460x215), mas sempre existe
        # e e sempre a arte principal. `background_raw` varia MUITO de jogo pra
        # jogo - no Helldivers e a arte grande e viva, no Call of Duty e a
        # mesma arte escurecida e borrada. Por isso ela vai de FUNDO, atras da
        # capa, nunca como o banner em si.
        imagem_header=dados.get("header_image"),
        imagem_fundo=dados.get("background_raw") or dados.get("background"),
        generos=generos,
        desenvolvedora=", ".join(dados.get("developers") or []) or None,
        preco_atual=(preco.get("final") / 100) if preco.get("final") is not None else None,
        moeda=preco.get("currency"),
        gratuito=gratuito,
        no_nosso_banco=bool(no_banco),
        ofertas=ofertas,
        menor_historico=menor_historico,
    )

    return bloco, jogo_ao_vivo


GATILHOS: dict[str, tuple[str, ...]] = {
    "steam": ("steam", "jogo", "jogos", "preco", "preço", "catalogo", "catálogo",
              "jogadores simultaneos", "ccu", "genero", "gênero", "desconto"),
    "partidas": ("partida", "partidas", "dota", "torneio", "liga", "duracao",
                 "duração", "radiant", "dire", "esport"),
    "herois": ("heroi", "herói", "herois", "heróis", "winrate", "personagem", "meta"),
    "modelos": ("modelo", "modelos", "previsao", "previsão", "prever", "acuracia",
                "acurácia", "roc", "auc", "treino", "machine learning", "ml",
                "confronto", "confrontos", "quem ganha", "quem vence", "favorito"),
    "sentimento": ("sentimento", "avaliacao", "avaliação", "avaliacoes", "avaliações",
                   "review", "reviews", "positiva", "negativa", "nlp"),
}


@dataclass
class ContextoMontado:
    blocos: list[Bloco]
    #: Populado so quando a pergunta pede recomendacao - ver `_bloco_recomendacao`.
    recomendacoes: list[JogoRecomendado] = field(default_factory=list)
    #: Populado so quando a pergunta cita um jogo identificavel - ver `_bloco_steam_ao_vivo`.
    jogo_ao_vivo: JogoAoVivo | None = None
    #: Os numeros dos blocos, estruturados - a tela desenha grafico com eles.
    series: list[SerieAssistente] = field(default_factory=list)


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

    construtores: dict[str, Callable[[Any], tuple[Bloco, SerieAssistente | None]]] = {
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
        series: list[SerieAssistente] = []
        for chave in ("steam", "partidas", "herois", "sentimento"):
            if chave in escolhidos:
                bloco, serie = construtores[chave](sessao)
                blocos.append(bloco)
                if serie is not None and serie.itens:
                    series.append(serie)

        elenco, serie_elenco = _bloco_elenco(pergunta, sessao)
        if elenco is not None:
            blocos.append(elenco)
            if serie_elenco is not None and serie_elenco.itens:
                # Na frente pelo mesmo motivo da descoberta: a tela desenha
                # `series[0]`, e quem pergunta de agente do Valorant nao quer o
                # grafico de winrate de heroi de Dota ao lado da resposta.
                series.insert(0, serie_elenco)

        guia = _bloco_guia(pergunta, sessao)
        if guia is not None:
            blocos.append(guia)

        if "modelos" in escolhidos:
            blocos.append(_bloco_modelos(pergunta, sessao))

        ao_vivo, jogo_ao_vivo = _bloco_steam_ao_vivo(pergunta, sessao)
        if ao_vivo is not None:
            blocos.append(ao_vivo)

        # A descoberta na loja tem precedencia sobre a recomendacao do
        # catalogo, e as duas nunca entram juntas. Quando a pergunta pede
        # "FPS pra jogar com amigos", o bloco do catalogo responderia "os mais
        # bem avaliados que monitoramos" - outra pergunta - e a tela mostraria
        # dois blocos de recomendacao discordando, o mesmo defeito que ja
        # apareceu entre recomendacao e extremo de avaliacao.
        descoberta, recomendacoes, serie_descoberta = _bloco_descoberta(pergunta)
        if descoberta is not None:
            blocos.append(descoberta)
            if serie_descoberta is not None and serie_descoberta.itens:
                # Na FRENTE das outras: a tela desenha `series[0]`, e a serie
                # que responde a pergunta e esta. Anexada no fim, o grafico
                # mostraria os jogadores dos jogos do NOSSO catalogo ao lado de
                # uma resposta sobre jogos da loja - o grafico contradizendo o
                # texto, que e a falha que este projeto menos pode ter.
                series.insert(0, serie_descoberta)
        else:
            recomendacao, recomendacoes = _bloco_recomendacao(pergunta, sessao)
            if recomendacao is not None:
                blocos.append(recomendacao)

    # Nao depende de sessao (e so rede, ver steam_loja.extremo_avaliacao_por_genero).
    extremo = _bloco_extremo_avaliacao(pergunta)
    if extremo is not None:
        blocos.append(extremo)

    return ContextoMontado(
        blocos=[bloco for bloco in blocos if bloco.conteudo.strip()],
        recomendacoes=recomendacoes,
        jogo_ao_vivo=jogo_ao_vivo,
        series=series,
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
        jogo_ao_vivo=contexto_montado.jogo_ao_vivo,
        series=contexto_montado.series,
        tokens_entrada=uso.get("prompt_tokens"),
        tokens_saida=uso.get("completion_tokens"),
    )
