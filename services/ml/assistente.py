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
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import requests
from sqlalchemy import Integer, cast, desc, func, select

from models import vocabulario_esports
from services.collectors import itad_loja, opgg_mcp, steam_descoberta, steam_loja
from config import get_settings
from services.ml import telemetria_assistente
from services.collectors.steam_online import URL_MAIS_JOGADOS as URL_MAIS_JOGADOS_STEAM
from models.models import (
    AgendaPartida,
    DimAppSteamNome,
    DimEquipe,
    DimJogo,
    DimJogoSteam,
    DimJogoXbox,
    DimPartida,
    DimPersonagem,
    FatoAvaliacaoSteam,
    FatoEstatisticaPersonagem,
    FatoPartidaJogador,
    FatoSnapshotJogoSteam,
    FatoSteamOnline,
    RankingExterno,
)
from models.session import session_scope
from services.etl.transform_itad import MenorHistorico, OfertaItad
from services.ml.confronto import carregar_relatorio as relatorio_confronto
from services.ml.confronto import jogos_com_modelo as _jogos_com_modelo_confronto
from services.ml.confronto import prever as prever_confronto
from services.ml.sentimento import carregar_metricas as metricas_sentimento

logger = logging.getLogger(__name__)

INSTRUCAO = """\
Você é o assistente de dados do PlayDB, uma plataforma de coleta e análise de \
dados de jogos e esports.

O QUE É O PLAYDB, e o que você é dentro dele. A plataforma coleta por conta \
própria: as lojas (Steam e Xbox/Game Pass), o calendário e os resultados do \
cenário profissional de vários jogos, os rankings oficiais que cada esporte \
publica, as avaliações da Steam, e treina aqui os modelos (sentimento das \
reviews e previsão de confronto). A proposta dela é uma só: **todo número \
mostrado tem origem conferível**. Você é o atalho para esse acervo - quem \
pergunta aqui está pedindo o que as telas mostram, sem precisar navegar. \
Então duas obrigações andam juntas: nunca inventar número, e nunca dizer \
"não temos isso" sobre algo que a plataforma tem. O bloco "O que o PlayDB \
faz e onde fica cada coisa" lista as telas e as rotas - é ele que diz o que \
existe, não o seu conhecimento geral sobre sites parecidos.

REGRA 0, acima de todas - ESCOPO. Você SÓ trata do mundo dos jogos e esports: \
jogos de qualquer plataforma, lojas e preços, partidas, torneios, times, \
jogadores e pro players, personagens/heróis/agentes, patches, meta, streamers, \
e a própria plataforma PlayDB. Se a pergunta for de OUTRO assunto \
(história, política, ciência, geografia, culinária, celebridades de fora dos \
games, conselhos de vida, matemática...), sua resposta inteira deve ser SÓ \
esta linha, nada mais: FORA_ESCOPO
Na dúvida entre "é de jogos" e "não é", trate como sendo de jogos e responda. \
Um nome próprio junto de "pro player", "jogador", "time", "campeonato" ou de um \
jogo (mesmo com erro de digitação) É do escopo.

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
- RANKING: o ranking que a fonte OFICIAL de cada esporte publica (Valve em \
Counter-Strike, vlr.gg em VALORANT, Ubisoft em Rainbow Six, LoL Esports, \
RLCS, DLTV). É de terceiro, tem data de snapshot, e NÃO é a mesma coisa que \
a força estimada pelo nosso modelo.
- XBOX: o catálogo da Microsoft Store que coletamos, focado no Game Pass - \
preço em BRL, desconto, se está no Game Pass agora e a nota da Store (0 a 5, \
escala diferente do percentual da Steam).

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
13. Quando houver um bloco "Elenco e desempenho de X - OP.GG", ele responde "melhor campeão/agente" e "meta" desse jogo. Use os números dele, diga "segundo o OP.GG" e que é do público geral com classificação, NÃO do cenário profissional. Se a pergunta for sobre o meta PROFISSIONAL/competitivo, diga que esse recorte não responde isso. Se o mapa de capacidade diz que o jogo TEM desempenho por personagem mas NENHUM bloco com esses números veio no contexto, NÃO invente winrate, pick rate ou nomes: diga que o dado existe na tela /herois e que nesta resposta ele não foi carregado.
14. Quando houver um bloco "Guia de build - X", ele responde "como jogar / o que buildar / ordem de subir a habilidade / runas" desse personagem. Liste os itens por fase, a prioridade de habilidade e as runas COMO ESTÃO no bloco. É dado do OP.GG/OpenDota (público geral), não do cenário profissional, e é da última coleta - não é ao vivo.
15. Quando houver um bloco "Modelo de confronto", ele diz para quais jogos existe modelo de previsão ajustado. Se a pergunta pedir previsão de um confronto de um jogo SEM modelo na lista, diga que ainda não há modelo para esse jogo. Se o bloco disser que a acurácia não supera a taxa base, a resposta precisa dizer isso - não venda a previsão como confiável.
16. BUSCA NA WEB. Antes de responder, decida nesta ordem: (a) a pergunta é do mundo dos jogos/esports? Se NÃO -> só "FORA_ESCOPO" (regra 0). (b) O CONTEXTO responde? Se responde, responda normalmente. (c) Se é de jogos mas o CONTEXTO não tem (resultado/campeão de torneio, quem é um jogador, notícia, data de lançamento, patch atual, comparação entre jogos que não temos) -> sua resposta inteira deve ser SÓ esta linha: PRECISA_WEB
17. Numa resposta em MODO WEB (o sistema avisa), os resultados da busca já vêm no contexto. Use-os, inclusive números, MAS: (a) atribua cada afirmação à fonte - "segundo <site/página>", nunca como medição nossa; (b) se os resultados forem rasos, velhos ou se contradisserem, diga que a web não deu resposta firme; (c) não vá além do que os resultados dizem. Sem nada útil na web, aí sim a regra 3.
18. O CONTEXTO pode trazer um bloco que a pergunta não pediu (ex.: o catálogo da Steam ordenado por jogadores simultâneos). Cite um bloco SÓ se ele responde a pergunta feita. Em especial, não mencione "jogos mais jogados agora"/ranking de jogadores simultâneos a menos que a pergunta seja sobre isso - citar esse número por conta própria, numa pergunta sobre outro assunto ou outro jogo, é o erro que a regra 0 e as regras acima existem para evitar.
19. ONDE VER. Ao indicar uma tela, use a rota EXATA do bloco "O que o PlayDB faz e onde fica cada coisa" (ex.: /catalogo/xbox, /esports/counterstrike/ranking). Rota com placeholder (/esports/<jogo>/partidas, /steam/<app_id>, /xbox/<product_id>) NUNCA vai assim para a resposta: troque pelo valor real - o código do jogo está no mesmo bloco, e o app_id/product_id aparece no bloco do jogo. Se você não tem o valor, escreva o nome da tela ("a aba Partidas de E-Sports") em vez de um link quebrado. Nunca invente rota, nome de menu ou botão, e nunca prometa recurso que esse bloco não lista - se a pessoa pedir algo que a plataforma não faz (PlayStation, comprar o jogo, ver a conta dela da Steam), diga o que existe no lugar. Indicar a tela é um COMPLEMENTO da resposta, não a resposta: primeiro responda com o dado do contexto.
20. AGENDA. Quando houver um bloco de agenda, ele responde "quando joga", "tem jogo hoje" e "o que está rolando". Use os horários COMO ESTÃO lá (já vêm em horário de Brasília) e diga o torneio. Se o bloco disser que não há confronto futuro na janela, diga isso - não ofereça a partida de outro time nem invente data. Confronto listado como "deve estar em andamento" é inferência pelo horário, não confirmação de que está ao vivo: diga assim.
21. RANKING OFICIAL. Com um bloco de ranking, responda "qual o melhor time" por ELE, citando a fonte e a data do snapshot ("#1 no ranking da Valve, snapshot de ..."). O bloco diz a REGIÃO de cada lista: quando o ranking é regional (VALORANT, LoL, Rocket League), diga de qual região está falando - "o #1 da Europa" e "o #1 do mundo" são respostas diferentes, e dar uma pela outra é erro de fato. Não misture com a força do nosso modelo nem com winrate das nossas partidas - são medidas diferentes, e trocá-las é responder outra pergunta.
22. PREVISÃO DE CONFRONTO. Com um bloco de previsão, a resposta é a probabilidade DELE, com os dois nomes e os fatores que pesaram. Se o bloco avisar que a acurácia não supera a taxa base ou que a amostra é pequena, a resposta PRECISA dizer isso na mesma frase da porcentagem. Se o bloco disser que falta histórico do par, diga que não há previsão para esse confronto - nunca estime a chance por conta própria.
23. XBOX E GAME PASS. Com um bloco do Xbox, responda por ele, não pelo seu conhecimento geral - entra e sai jogo do Game Pass toda semana, e o bloco é a coleta mais recente. A nota da Store é de 0 a 5 e não se compara com o percentual de positivas da Steam: não converta uma na outra. Jogo ausente do bloco significa "não está na nossa coleta", nunca "não existe no Xbox".
24. STEAM INTEIRA x NOSSO CATÁLOGO. São duas perguntas diferentes e cada uma tem o seu bloco. "Qual o jogo mais jogado agora" (o mundo) se responde pelo bloco da Valve ao vivo; "qual o mais jogado do catálogo de vocês" se responde pelo bloco do catálogo. Diga sempre de qual recorte está falando, e não apresente o catálogo de 60 jogos como se fosse a Steam inteira.
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
    #: As paginas que a busca da web trouxe (quando ela disparou): `{url,
    #: titulo}`. A tela mostra como links - a resposta cita, a fonte fica a um
    #: clique.
    fontes_web: list[dict[str, str]] = field(default_factory=list)
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    #: `True` quando `perguntar()` recebeu `chave_pessoal` - a resposta usou
    #: uma chave de IA da propria conta, nao a compartilhada do site.
    usando_chave_propria: bool = False
    #: "openrouter" | "anthropic" | "google" - so preenchido junto com
    #: `usando_chave_propria`.
    provedor_ia: str | None = None


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


#: As telas do site, na ordem da navegacao. Rota exata + o que ela responde.
#: E texto fixo de proposito: rota de tela nao esta em tabela nenhuma, e a
#: alternativa (deixar o modelo deduzir) produz link inventado - o defeito que
#: este bloco existe para fechar.
TELAS_PLAYDB = (
    ("/", "Visão Geral",
     "o dia de hoje: usuários simultâneos da Steam inteira (número da Valve), "
     "Top mais jogados agora, próximas partidas e destaques"),
    ("/catalogo/steam", "Catálogo de Jogos > Steam",
     "os jogos da Steam que monitoramos: preço, jogadores simultâneos, nota, "
     "gênero. A ficha de um jogo fica em /steam/<app_id>"),
    ("/catalogo/xbox", "Catálogo de Jogos > Xbox",
     "jogos da Microsoft Store: preço, desconto, Game Pass, nota da loja. "
     "A ficha fica em /xbox/<product_id>"),
    ("/catalogo/playstation", "Catálogo de Jogos > PlayStation",
     "AINDA NÃO EXISTE - a aba mostra 'em breve'. Não há nenhum dado de "
     "PlayStation nesta plataforma"),
    ("/recomendacoes", "Recomendações por Reviews",
     "recomendação a partir das avaliações da Steam, com resumo por IA e o "
     "modelo de sentimento"),
    ("/esports/<jogo>/partidas", "E-Sports > Partidas",
     "a agenda: os próximos confrontos daquele jogo, com torneio e horário"),
    ("/esports/<jogo>/resultados", "E-Sports > Resultados",
     "confrontos já decididos, com placar e (onde a fonte publica) o detalhe "
     "por mapa e por jogador"),
    ("/esports/<jogo>/previsao", "E-Sports > Previsão",
     "o simulador: escolhe dois times e mostra a probabilidade de cada um "
     "vencer, com os fatores por trás"),
    ("/esports/<jogo>/ranking", "E-Sports > Ranking",
     "as equipes ordenadas - por força ajustada pelos nossos confrontos e, "
     "onde existe, pelo ranking oficial publicado"),
    ("/esports/<jogo>/herois", "E-Sports > Heróis",
     "personagens/agentes/campeões: winrate, taxa de escolha e a ficha "
     "completa (habilidades e, onde há, guia de build)"),
    ("/esports/<jogo>/jogadores", "E-Sports > Jogadores",
     "os jogadores com desempenho agregado das partidas coletadas"),
    ("/assistente", "Assistente de IA",
     "esta tela - responde sobre os dados da plataforma"),
    ("/perfil", "Perfil",
     "a conta: favoritar jogos (acompanha preço, promoção e notícia) e times "
     "(acompanha a próxima partida), e cadastrar uma chave de IA própria. "
     "Exige login"),
    ("/mobile.html", "APK Mobile", "o aplicativo Android da plataforma"),
)


def _bloco_plataforma(sessao) -> Bloco:
    """O que o PlayDB é e onde cada resposta mora no site.

    Entra em TODA pergunta, junto do bloco geral. Existe por duas falhas que
    apareceram juntas: o assistente mandava a pessoa para telas que não
    existem (inventava rota e nome de menu), e respondia "não temos isso"
    sobre coisa que a plataforma faz - porque nenhum bloco falava das TELAS,
    só dos números. Um assistente que não sabe o que o próprio site oferece
    não consegue ser o atalho para ele.

    O texto das telas é fixo (`TELAS_PLAYDB`); o que vem do banco é só quais
    jogos têm área de esports de fato, que muda com a coleta.
    """
    # Mesmo criterio e mesma ordem do trilho lateral e do menu de E-Sports
    # (`temEsports` no front): jogo com partida, agenda OU equipe coletada.
    # Ordenar igual importa - a pessoa ve os 8 primeiros na lateral, e o
    # assistente falando de outra ordem parece falar de outro site.
    partidas_de = (
        select(func.count())
        .select_from(DimPartida)
        .where(DimPartida.id_jogo == DimJogo.id_jogo)
        .scalar_subquery()
    )
    agenda_de = (
        select(func.count())
        .select_from(AgendaPartida)
        .where(AgendaPartida.id_jogo == DimJogo.id_jogo)
        .scalar_subquery()
    )
    equipes_de = (
        select(func.count())
        .select_from(DimEquipe)
        .where(DimEquipe.id_jogo == DimJogo.id_jogo)
        .scalar_subquery()
    )
    com_area = sessao.execute(
        select(DimJogo.codigo, DimJogo.nome)
        .where((partidas_de > 0) | (agenda_de > 0) | (equipes_de > 0))
        .order_by(desc(partidas_de), desc(agenda_de), desc(equipes_de), DimJogo.nome)
    ).all()

    linhas = [
        "O PlayDB é uma plataforma de coleta e análise de dados de jogos e "
        "esports (projeto de TCC). Tudo que ele mostra vem de coleta própria: "
        "lojas (Steam e Xbox), fontes de esports e modelos treinados aqui - "
        "não é agregador de notícia nem loja.",
        "",
        "TELAS DO SITE (ao indicar onde ver, use a rota exata desta lista e "
        "nunca invente outra):",
    ]
    linhas += [f"- {rotulo} ({rota}): {descricao}." for rota, rotulo, descricao in TELAS_PLAYDB]

    if com_area:
        linhas += [
            "",
            "Jogos com área de E-Sports própria (troque <jogo> pelo código; os "
            "8 primeiros são os que aparecem no menu lateral, os demais ficam "
            "no menu de E-Sports): "
            + ", ".join(f"{nome} = {codigo}" for codigo, nome in com_area)
            + ".",
        ]

    linhas += [
        "",
        "O QUE A PLATAFORMA NÃO FAZ: não vende, não instala e não roda jogo; "
        "não acessa a conta de Steam/Xbox de ninguém; não tem dado de "
        "PlayStation, Nintendo nem de loja fora Steam/Xbox (o preço de outras "
        "lojas só aparece na ficha de um jogo da Steam, via IsThereAnyDeal); "
        "não cobre partida ranqueada pessoal de quem pergunta - o cenário "
        "coberto é o profissional, e o público geral só aparece via OP.GG.",
    ]

    return Bloco("plataforma", "O que o PlayDB faz e onde fica cada coisa", "\n".join(linhas))


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


#: Apelido -> `dim_jogo.codigo`. "qual o melhor campeao de LoL" nunca escreve
#: "League of Legends" por extenso, e sem isto o bloco de desempenho nao
#: disparava - e o modelo, vendo no mapa de capacidade que LoL TEM desempenho,
#: inventava os numeros.
APELIDOS_JOGO: dict[str, str] = {
    "lol": "leagueoflegends",
    "league": "leagueoflegends",
    "league of legends": "leagueoflegends",
    "valorant": "valorant",
    "valo": "valorant",
    "val": "valorant",
    "dota": "dota2",
    "dota 2": "dota2",
    "cs": "counterstrike",
    "csgo": "counterstrike",
    "cs2": "counterstrike",
    "cs go": "counterstrike",
    "counter strike": "counterstrike",
    "counter-strike": "counterstrike",
}


def _codigos_citados(pergunta: str) -> set[str]:
    """Os `dim_jogo.codigo` que a pergunta cita, por nome ou apelido."""
    normalizada = _normalizar(pergunta)
    return {
        codigo
        for apelido, codigo in APELIDOS_JOGO.items()
        if re.search(rf"\b{re.escape(apelido)}\b", normalizada)
    }


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

    codigos_apelido = _codigos_citados(pergunta)
    alvo = None
    for id_jogo, codigo, nome, partidas in candidatos:
        if partidas:
            continue
        if _normalizar(nome) in trechos or codigo in codigos_apelido:
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
            "metricas": dict(metricas or {}),
        }

    # `pick_rate` nem sempre esta no JSONB de metricas (o de Valorant guarda so
    # HS%/ADR/...), mas a proporcao de partidas sempre da pra derivar - e e o
    # que ordena a lista e desenha o grafico. Sobre o total de participacoes,
    # nao de partidas: cada partida tem varios personagens.
    total = sum(d["partidas"] for d in saida.values())
    if total:
        for d in saida.values():
            d["metricas"].setdefault(
                "pick_rate", round(100 * d["partidas"] / total, 1)
            )
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


def _extremo_recepcao_pedido(pergunta: str) -> str | None:
    """`"pior"`/`"melhor"` para ordenar a LISTA/GRAFICO do bloco de sentimento
    (o NOSSO catalogo - poucos jogos, cabe todo na resposta).

    Mais solto que `_extremo_avaliacao_pedido` (que exige "pior avaliacao"/
    "pior nota" etc por extenso, porque aquele bloco fala de TODA a Steam via
    SteamSpy e "pior" sozinho la seria perigoso demais). Aqui e seguro: esta
    funcao so e chamada de dentro de `_bloco_sentimento`, que so se monta
    quando a pergunta ja tem gatilho de avaliacao/review/sentimento - "pior"/
    "melhor" soltos aqui sempre se referem a recepcao, nunca a outra coisa.

    Existe porque "qual jogo tem a pior recepcao nas avaliacoes" nao bate
    nenhum termo de `GATILHOS_EXTREMO_AVALIACAO` (fala "recepcao", nao
    "avaliacao"/"nota") - sem isto, o bloco monta a lista/grafico padrao
    (por VOLUME de avaliacoes, nao por nota), e o texto (que le a lista
    inteira) cita um jogo enquanto o grafico mostra outro.
    """
    normalizada = _normalizar(pergunta)
    if (
        re.search(r"\bpior(es)?\b", normalizada)
        or "menos aprovado" in normalizada
        or "mais reprovado" in normalizada
        or "mais mal" in normalizada
    ):
        return "pior"
    if (
        re.search(r"\bmelhor(es)?\b", normalizada)
        or "mais aprovado" in normalizada
        or "mais bem" in normalizada
    ):
        return "melhor"
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


GATILHOS_PREVISAO = (
    "quem ganha", "quem vence", "quem leva", "quem e favorito", "favorito",
    "chance de vencer", "chances de", "probabilidade", "previsao", "prever",
    "quem e melhor", "quem ganharia", "contra", " vs ", " x ",
    "confronto entre", "simular", "simulacao",
)


def _pede_previsao(pergunta: str) -> bool:
    normalizada = f" {_normalizar(pergunta)} "
    return any(_normalizar(termo) in normalizada for termo in GATILHOS_PREVISAO)


def _bloco_previsao(pergunta: str, sessao) -> Bloco | None:
    """A previsao REAL do nosso modelo para dois times citados na pergunta.

    A tela /esports/<jogo>/previsao responde "quem ganha X contra Y" com
    probabilidade e fatores; o assistente so tinha as METRICAS do modelo
    (acuracia, ROC-AUC) - entao "quem ganha FURIA x MIBR?" virava uma aula
    sobre validacao, ou pior, um palpite do conhecimento geral. Agora roda o
    mesmo motor da tela.

    O aviso de validacao vem junto, sempre: com a amostra atual a acuracia
    nem sempre supera a taxa base, e vender a porcentagem sem esse contexto e
    exatamente o que esta plataforma existe para nao fazer.
    """
    if not _pede_previsao(pergunta):
        return None

    com_modelo = _jogos_com_modelo_confronto()
    if not com_modelo:
        return None

    # `confrontos` separa o time de verdade do homonimo de academia: "Team
    # Spirit" e "Team Spirit Academy" casam os dois com "spirit", e sem um
    # criterio de proeminencia a previsao sai do time errado com cara de
    # certa. Quem tem mais confronto coletado e quem a pergunta quer dizer.
    confrontos_de = (
        select(func.count())
        .select_from(AgendaPartida)
        .where(
            (AgendaPartida.id_equipe_a == DimEquipe.id_equipe)
            | (AgendaPartida.id_equipe_b == DimEquipe.id_equipe)
        )
        .scalar_subquery()
    )
    candidatos = sessao.execute(
        select(
            DimEquipe.id_equipe,
            DimEquipe.nome,
            DimJogo.codigo,
            DimJogo.nome,
            confrontos_de,
        )
        .join(DimJogo, DimJogo.id_jogo == DimEquipe.id_jogo)
        .where(DimJogo.codigo.in_(com_modelo))
    ).all()
    if not candidatos:
        return None

    citados = _equipe_citada(pergunta, {linha[1] for linha in candidatos})
    if len(citados) < 2:
        return None

    normalizada = _normalizar(pergunta)
    tokens = re.findall(r"[a-z0-9]+", normalizada)
    trechos = {
        " ".join(tokens[i:j])
        for i in range(len(tokens))
        for j in range(i + 1, min(i + 4, len(tokens)) + 1)
    }
    codigos = _codigos_citados(pergunta)

    def _intervalo(nome: str) -> tuple[int, int]:
        """O trecho da pergunta onde este time foi citado.

        Intervalo, nao posicao: "Team Spirit" e "Spirit" sao duas linhas do
        banco para a MESMA mencao no texto, e agrupa-las por posicao exata as
        tratava como dois lados de um confronto ("Team Spirit x Spirit").
        """
        alvo = _normalizar(nome)
        indice = normalizada.find(alvo)
        if indice >= 0:
            return (indice, indice + len(alvo))
        for palavra in re.findall(r"[a-z0-9]+", alvo):
            if len(palavra) >= 4:
                achado = normalizada.find(palavra)
                if achado >= 0:
                    return (achado, achado + len(palavra))
        return (10_000, 10_000)

    #: Um "grupo" e o time que a pergunta quis dizer: entre os homonimos, o de
    #: nome exato e, empatando, o de mais confrontos coletados.
    def _melhor(linhas: list) -> tuple:
        return sorted(
            linhas,
            key=lambda linha: (
                0 if _normalizar(linha[1]) in trechos else 1,
                -(linha[4] or 0),
                len(linha[1]),
            ),
        )[0]

    por_jogo: dict[str, list[tuple[tuple[int, int], Any]]] = {}
    for linha in candidatos:
        if linha[1] not in citados:
            continue
        por_jogo.setdefault(linha[2], []).append((_intervalo(linha[1]), linha))

    def _mencoes(marcados: list[tuple[tuple[int, int], Any]]) -> list[list]:
        """Uma lista por MENÇÃO do texto - trechos que se sobrepõem viram uma."""
        grupos: list[tuple[list[int], list]] = []
        for (inicio, fim), linha in sorted(marcados, key=lambda item: item[0]):
            if grupos and inicio < grupos[-1][0][1]:
                grupos[-1][0][1] = max(grupos[-1][0][1], fim)
                grupos[-1][1].append(linha)
            else:
                grupos.append(([inicio, fim], [linha]))
        return [linhas for _, linhas in grupos]

    escolha = None
    for codigo, marcados in por_jogo.items():
        if codigos and codigo not in codigos:
            continue
        grupos = _mencoes(marcados)
        if len(grupos) < 2:
            continue
        lados = [_melhor(linhas) for linhas in grupos[:2]]
        if lados[0][0] == lados[1][0]:
            continue
        escolha = (codigo, lados)
        break
    if escolha is None:
        return None

    codigo_jogo, lados = escolha
    id_a, nome_a, _, nome_jogo, _ = lados[0]
    id_b, nome_b, _, _, _ = lados[1]

    try:
        previsao = prever_confronto(id_a, id_b, codigo_jogo)
    except KeyError:
        return Bloco(
            "previsao",
            f"Previsao de {nome_a} x {nome_b} ({nome_jogo})",
            f"O modelo de {nome_jogo} nao tem confronto coletado de "
            f"{nome_a} e/ou {nome_b}, entao NAO ha previsao para este par. "
            "Diga isso - nao estime a chance por conta propria - e indique a "
            f"aba Previsao em /esports/{codigo_jogo}/previsao, que lista os "
            "times com histórico suficiente.",
        )
    except ValueError:
        return None

    relatorio = relatorio_confronto(codigo_jogo) or {}
    validacao = relatorio.get("validacao") or {}

    a, b = previsao.equipe_a, previsao.equipe_b
    linhas = [
        f"Previsao do NOSSO modelo (Bradley-Terry + regressao logistica sobre "
        f"os confrontos de {nome_jogo} que coletamos) - a mesma da aba "
        f"Previsao em /esports/{codigo_jogo}/previsao.",
        f"{a.nome} vence: {round(previsao.probabilidade_a * 100, 1)}%",
        f"{b.nome} vence: {round(previsao.probabilidade_b * 100, 1)}%",
        f"{a.nome}: {a.vitorias} vitorias em {a.partidas} confrontos coletados "
        f"(winrate {round(a.winrate, 1)}%, forca {round(a.forca, 3)})"
        + (f", #{a.posicao_ranking} no ranking oficial" if a.posicao_ranking else ""),
        f"{b.nome}: {b.vitorias} vitorias em {b.partidas} confrontos coletados "
        f"(winrate {round(b.winrate, 1)}%, forca {round(b.forca, 3)})"
        + (f", #{b.posicao_ranking} no ranking oficial" if b.posicao_ranking else ""),
        f"Confrontos diretos coletados: {previsao.confrontos_diretos} "
        f"({previsao.vitorias_diretas_a} vitorias de {a.nome}).",
    ]

    if previsao.fatores:
        linhas.append("Fatores que o modelo pesa:")
        for fator in previsao.fatores[:5]:
            linhas.append(
                f"  {fator.rotulo}: {a.nome} {fator.valor_a}, {b.nome} "
                f"{fator.valor_b} ({fator.unidade or 'sem unidade'})"
            )

    if validacao.get("suficiente"):
        acuracia = round(validacao["acuracia"] * 100, 1)
        base = round(validacao["taxa_base"] * 100, 1)
        linhas.append(
            f"Validacao temporal deste modelo: acuracia {acuracia}% contra "
            f"taxa base de {base}% em {validacao['avaliadas']} partidas."
        )
        if validacao["acuracia"] <= validacao["taxa_base"]:
            linhas.append(
                "ATENCAO: a acuracia NAO supera a taxa base. A resposta "
                "precisa dizer que esta previsao e descritiva e nao demonstrou "
                "prever melhor que o chute."
            )
    else:
        linhas.append(
            "Amostra pequena demais para validar este modelo: trate a "
            "probabilidade como descritiva, nao como acerto comprovado."
        )

    return Bloco(
        "previsao",
        f"Previsao de {a.nome} x {b.nome} ({nome_jogo})",
        "\n".join(linhas),
    )


GATILHOS_STEAM_ONLINE = (
    "mais jogado", "mais jogados", "top da steam", "top steam",
    "ranking da steam", "quem lidera a steam", "jogo mais jogado",
    "usuarios online", "usuarios simultaneos da steam", "pessoas jogando",
    "quantas pessoas estao jogando", "online agora", "steam agora",
    "pico de jogadores", "top 10 da steam", "mais populares",
)

#: Cache de processo do Top da Valve. Mesmo TTL do endpoint `/api/steam/
#: mais-jogados`: a Valve mexe no numero a cada poucos minutos, e segurar 90s
#: evita uma chamada de rede por pergunta sem a lista ficar velha.
_CACHE_TOP_STEAM: dict[str, Any] = {"em": 0.0, "itens": []}
_TTL_TOP_STEAM_S = 90


def _pede_steam_online(pergunta: str) -> bool:
    normalizada = _normalizar(pergunta)
    return any(_normalizar(termo) in normalizada for termo in GATILHOS_STEAM_ONLINE)


def _top_steam_ao_vivo() -> list[dict[str, Any]]:
    """Os mais jogados da Steam INTEIRA agora, direto da Valve.

    Rede, como `_bloco_extremo_avaliacao`. Falha em silencio (lista vazia):
    ficar sem este bloco e melhor que a pergunta inteira falhar por causa de
    uma indisponibilidade da Valve.
    """
    agora = time.monotonic()
    if agora - float(_CACHE_TOP_STEAM["em"]) < _TTL_TOP_STEAM_S and _CACHE_TOP_STEAM["itens"]:
        return _CACHE_TOP_STEAM["itens"]

    try:
        resposta = requests.get(URL_MAIS_JOGADOS_STEAM, timeout=8)
        resposta.raise_for_status()
        ranks = ((resposta.json() or {}).get("response") or {}).get("ranks") or []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Top da Steam indisponivel para o assistente: %s", exc)
        return _CACHE_TOP_STEAM["itens"]

    itens = [
        {
            "posicao": linha["rank"],
            "app_id": linha["appid"],
            "jogadores": linha.get("concurrent_in_game") or 0,
            "pico_24h": linha.get("peak_in_game"),
        }
        for linha in ranks
        if isinstance(linha.get("appid"), int)
    ]
    if itens:
        _CACHE_TOP_STEAM["em"] = agora
        _CACHE_TOP_STEAM["itens"] = itens
    return itens


def _bloco_steam_online(pergunta: str, sessao) -> tuple[Bloco | None, SerieAssistente | None]:
    """Os mais jogados da STEAM INTEIRA agora + quanta gente esta na Steam.

    Este bloco e o que separa duas perguntas que o assistente confundia:
    "qual o jogo mais jogado agora" (a Steam inteira - Counter-Strike, Dota,
    PUBG, o que a Valve publica neste instante) e "qual o mais jogado do
    catalogo de voces" (os 60 jogos que monitoramos). O segundo ja tinha
    bloco; o primeiro caia no catalogo e respondia errado com numero certo.
    """
    if not _pede_steam_online(pergunta):
        return None, None

    itens = _top_steam_ao_vivo()
    plataforma = sessao.execute(
        select(
            FatoSteamOnline.usuarios_online,
            FatoSteamOnline.usuarios_em_jogo,
            FatoSteamOnline.coletado_em,
        ).order_by(desc(FatoSteamOnline.coletado_em)).limit(1)
    ).first()

    if not itens and plataforma is None:
        return None, None

    linhas = [
        "FONTE: Valve, consultada agora - vale para a Steam INTEIRA, nao so "
        "para os jogos do nosso catalogo. Se a pergunta for sobre o NOSSO "
        "catalogo, o bloco certo e o do catalogo, nao este.",
    ]

    if plataforma is not None:
        online, em_jogo, coletado = plataforma
        linhas.append(
            f"Pessoas conectadas a Steam: {online} agora, sendo {em_jogo} "
            f"dentro de algum jogo (coleta de {_quando_texto(coletado, datetime.now(timezone.utc))})."
        )

    pontos: list[PontoSerie] = []
    if itens:
        ids = [item["app_id"] for item in itens[:20]]
        nomes = dict(
            sessao.execute(
                select(DimJogoSteam.app_id, DimJogoSteam.nome).where(
                    DimJogoSteam.app_id.in_(ids)
                )
            ).all()
        )
        for app_id, nome in sessao.execute(
            select(DimAppSteamNome.app_id, DimAppSteamNome.nome).where(
                DimAppSteamNome.app_id.in_(ids)
            )
        ).all():
            nomes.setdefault(app_id, nome)

        linhas.append("")
        linhas.append("Mais jogados da Steam neste instante (ranking da Valve):")
        for item in itens[:15]:
            nome = nomes.get(item["app_id"]) or f"app {item['app_id']}"
            pico = f", pico de {item['pico_24h']} em 24h" if item["pico_24h"] else ""
            linhas.append(
                f"  #{item['posicao']} {nome}: {item['jogadores']} jogando agora{pico}"
            )
            if item["jogadores"]:
                pontos.append(
                    PontoSerie(rotulo=nome, valor=float(item["jogadores"]))
                )

    serie = (
        SerieAssistente(
            chave="steam_online",
            titulo="Mais jogados da Steam agora (Valve)",
            unidade="jogadores",
            itens=pontos[:8],
        )
        if pontos
        else None
    )
    return (
        Bloco(
            "steam_online",
            "Steam inteira, ao vivo (Valve)",
            "\n".join(linhas),
            fonte="steam",
        ),
        serie,
    )


GATILHOS_XBOX = (
    "xbox", "game pass", "gamepass", "microsoft store", "series x", "series s",
    "console da microsoft",
)


def _pede_xbox(pergunta: str) -> bool:
    normalizada = _normalizar(pergunta)
    return any(_normalizar(termo) in normalizada for termo in GATILHOS_XBOX)


def _bloco_xbox(pergunta: str, sessao) -> Bloco | None:
    """O catalogo do Xbox: preco, desconto, Game Pass e nota da Store.

    A aba /catalogo/xbox existe desde a Fase 29 e nenhum bloco falava dela -
    perguntado "tem no Game Pass?", o assistente respondia pelo conhecimento
    geral (que envelhece: entra e sai jogo do Game Pass toda semana) ou dizia
    que a plataforma so cobre Steam. Cobre as duas.

    Com um jogo citado, responde por ELE. Sem jogo, faz o panorama - que e a
    resposta certa para "o que tem de bom no Game Pass?".
    """
    if not _pede_xbox(pergunta):
        return None

    catalogo = sessao.execute(
        select(
            DimJogoXbox.nome,
            DimJogoXbox.preco_atual,
            DimJogoXbox.preco_normal,
            DimJogoXbox.moeda,
            DimJogoXbox.desconto_percentual,
            DimJogoXbox.no_game_pass,
            DimJogoXbox.nota,
            DimJogoXbox.numero_avaliacoes,
            DimJogoXbox.generos,
            DimJogoXbox.gratuito,
        )
    ).all()
    if not catalogo:
        return None

    normalizada = _normalizar(pergunta)

    def _citado(nome: str) -> bool:
        alvo = _normalizar(nome)
        if len(alvo) >= 4 and alvo in normalizada:
            return True
        # "Avatar: Frontiers of Pandora" quando a pessoa escreve so "Avatar".
        raiz = _normalizar(nome.split(":")[0]).strip()
        return len(raiz) >= 5 and raiz in normalizada

    def _preco(linha) -> str:
        nome, preco, normal, moeda, desconto, game_pass, nota, avaliacoes, generos, gratuito = linha
        if gratuito:
            return "gratuito"
        if preco is None:
            return "preco nao publicado"
        texto = f"{moeda or 'BRL'} {preco}"
        if desconto:
            texto += f" ({desconto}% de desconto, de {moeda or 'BRL'} {normal})"
        return texto

    def _linha(linha) -> str:
        nome, preco, normal, moeda, desconto, game_pass, nota, avaliacoes, generos, gratuito = linha
        partes = [_preco(linha)]
        partes.append("NO Game Pass" if game_pass else "fora do Game Pass")
        if nota is not None:
            partes.append(f"nota {nota}/5 na Store em {avaliacoes or 0} avaliacoes")
        if generos:
            partes.append(", ".join(generos[:3]))
        return f"  {nome}: " + "; ".join(partes)

    citados = [linha for linha in catalogo if _citado(linha[0])]

    total = len(catalogo)
    no_gp = sum(1 for linha in catalogo if linha[5])
    cabecalho = (
        f"Catalogo do Xbox que coletamos: {total} jogos da Microsoft Store, "
        f"{no_gp} deles no Game Pass agora. A coleta e focada no Game Pass - "
        "um jogo de Xbox que nao esta nesta lista pode existir na loja sem "
        "estar aqui, entao nao afirme que ele 'nao existe no Xbox'. Preco em "
        "BRL, da ultima coleta. A nota e a da Microsoft Store (0 a 5), que NAO "
        "e a mesma escala do percentual de avaliacoes positivas da Steam."
    )

    if citados:
        corpo = ["Jogos do Xbox que a pergunta cita:"] + [
            _linha(linha) for linha in citados[:6]
        ]
        titulo = "Xbox - o jogo citado"
    else:
        promocoes = sorted(
            (linha for linha in catalogo if linha[4]),
            key=lambda linha: linha[4],
            reverse=True,
        )[:8]
        bem_avaliados = sorted(
            (
                linha
                for linha in catalogo
                if linha[6] is not None and (linha[7] or 0) >= 500
            ),
            key=lambda linha: (linha[6], linha[7] or 0),
            reverse=True,
        )[:8]
        corpo = []
        if promocoes:
            corpo.append("Maiores descontos agora no Xbox:")
            corpo += [_linha(linha) for linha in promocoes]
        if bem_avaliados:
            corpo.append("Melhores notas da Store (com 500+ avaliacoes):")
            corpo += [_linha(linha) for linha in bem_avaliados]
        titulo = "Xbox - panorama do catalogo"

    if not corpo:
        return None

    # `fonte` diz de ONDE LEMOS, nao quem publicou: isto sai do nosso banco
    # (a coleta do Xbox), e a tela pinta bloco de banco e bloco de loja ao
    # vivo de formas diferentes. A procedencia real esta no texto do bloco.
    return Bloco("xbox", titulo, cabecalho + "\n" + "\n".join(corpo))


GATILHOS_RANKING = (
    "ranking", "rankeado", "rankeada", "classificacao", "standings",
    "melhor time", "melhores times", "melhor equipe", "melhores equipes",
    "maior time", "maiores times", "top times", "top 10", "top 5",
    "numero 1", "primeiro lugar", "lider", "colocacao", "posicao",
    "melhor do mundo", "melhor da regiao",
)

#: Como cada fonte de ranking se chama para o leitor. Mesmo mapa do
#: `controllers/routers/ranking_oficial.py` - o nome que a tela mostra e o
#: nome que a resposta precisa citar, senao a pessoa nao consegue conferir.
FONTES_RANKING = {
    "vlr": "vlr.gg",
    "valve": "Valve Regional Standings",
    "ubi_r6": "R6 Esports Global Standings (Ubisoft)",
    "owcs": "OWCS (Liquipedia)",
    "rlcs": "RLCS (blast.tv)",
    "dltv": "DLTV World Ranking",
    "lolesports": "LoL Esports (oficial)",
}

#: Slug da regiao -> como se escreve na pergunta. Serve para "quem lidera o
#: ranking da Europa" achar `europe` sem o modelo ter que adivinhar.
APELIDOS_REGIAO = {
    "north-america": ("america do norte", "north america", "na", "eua"),
    "south-america": ("america do sul", "south america", "sul-americano"),
    "europe": ("europa", "europe", "europeu", "eu"),
    "brazil": ("brasil", "brazil", "brasileiro", "br"),
    "korea": ("coreia", "korea", "coreano"),
    "japan": ("japao", "japan", "japones"),
    "china": ("china", "chines"),
    "pacific": ("pacifico", "pacific"),
    "asia-pacific": ("asia", "asia-pacifico", "apac"),
    "mena": ("mena", "oriente medio"),
    "oceania": ("oceania", "oceanico"),
    "sub-saharan-africa": ("africa", "africano"),
    "la-s": ("latam sul", "la-s"),
    "la-n": ("latam norte", "la-n"),
    "lck": ("lck",),
    "lpl": ("lpl",),
    "lec": ("lec",),
    "lta-north": ("lta norte", "lta-north"),
    "lta-south": ("lta sul", "lta-south"),
    "cblol": ("cblol",),
    "ljl": ("ljl",),
    "lcp": ("lcp",),
    "nacl": ("nacl",),
    "lfl": ("lfl",),
    "vcs": ("vcs",),
    "global": ("global", "mundial", "do mundo"),
}


def _pede_ranking(pergunta: str) -> bool:
    normalizada = _normalizar(pergunta)
    return any(_normalizar(termo) in normalizada for termo in GATILHOS_RANKING)


def _regioes_citadas(pergunta: str) -> set[str]:
    normalizada = _normalizar(pergunta)
    tokens = set(re.findall(r"[a-z0-9-]+", normalizada))
    achadas: set[str] = set()
    for slug, apelidos in APELIDOS_REGIAO.items():
        for apelido in apelidos:
            if " " in apelido:
                if apelido in normalizada:
                    achadas.add(slug)
            elif apelido in tokens:
                achadas.add(slug)
    return achadas


def _bloco_ranking(pergunta: str, sessao) -> Bloco | None:
    """O ranking OFICIAL publicado da fonte de cada jogo (a aba Ranking).

    Nasce de "qual o melhor time de CS?", que antes caia no bloco de modelos
    (metricas de validacao, nao ranking) ou na web - com a Valve, o vlr.gg, a
    Ubisoft e a LoL Esports ja coletados no banco. E ranking de TERCEIRO, nao
    medicao nossa, e o bloco diz isso em cada linha para a resposta poder
    atribuir.

    Tres recortes, do mais especifico ao mais geral: a posicao de um time
    citado; o ranking do jogo (e da regiao) citado; ou o topo de cada jogo,
    quando a pergunta e generica - melhor que escolher um jogo no chute.
    """
    if not _pede_ranking(pergunta):
        return None

    ultima_por_jogo = (
        select(
            RankingExterno.id_jogo.label("id_jogo"),
            func.max(RankingExterno.data_referencia).label("data"),
        )
        .group_by(RankingExterno.id_jogo)
        .subquery()
    )
    linhas = sessao.execute(
        select(
            DimJogo.codigo,
            DimJogo.nome,
            RankingExterno.fonte,
            RankingExterno.regiao,
            RankingExterno.posicao,
            RankingExterno.equipe_nome,
            RankingExterno.pontos,
            RankingExterno.vitorias,
            RankingExterno.derrotas,
            RankingExterno.data_referencia,
        )
        .join(DimJogo, DimJogo.id_jogo == RankingExterno.id_jogo)
        .join(
            ultima_por_jogo,
            (ultima_por_jogo.c.id_jogo == RankingExterno.id_jogo)
            & (ultima_por_jogo.c.data == RankingExterno.data_referencia),
        )
        .where(RankingExterno.posicao <= 40)
        .order_by(DimJogo.codigo, RankingExterno.regiao, RankingExterno.posicao)
    ).all()

    if not linhas:
        return None

    codigos = _codigos_citados(pergunta)
    regioes = _regioes_citadas(pergunta)
    times = _equipe_citada(pergunta, {linha[5] for linha in linhas})

    def _descrever(linha) -> str:
        (_, _, fonte, regiao, posicao, equipe, pontos, vitorias, derrotas, _) = linha
        marca = (
            f"{pontos} pontos"
            if pontos is not None
            else f"{vitorias}V-{derrotas}D"
            if vitorias is not None
            else "sem pontuacao publicada"
        )
        return f"  #{posicao} {equipe} ({marca})"

    partes: list[str] = []

    if times:
        partes.append(
            "Onde os times citados aparecem nos rankings oficiais coletados:"
        )
        for linha in linhas:
            if linha[5] in times:
                fonte = FONTES_RANKING.get(linha[2], linha[2])
                partes.append(
                    f"  {linha[5]} - {linha[1]}, regiao {linha[3] or 'global'}: "
                    f"#{linha[4]} (fonte {fonte}, snapshot de {linha[9]})"
                )
        titulo = "Posicao no ranking oficial"
    else:
        alvo = [linha for linha in linhas if not codigos or linha[0] in codigos]
        if regioes:
            alvo = [linha for linha in alvo if (linha[3] or "global") in regioes] or alvo
        if not alvo:
            return None

        # Sem jogo citado a pergunta e generica ("qual o melhor time?"): o topo
        # de cada um, curto, em vez de escolher um jogo no chute.
        por_bloco = 10 if codigos else 3
        agrupado: dict[tuple[str, str | None], list] = {}
        for linha in alvo:
            agrupado.setdefault((linha[1], linha[3]), []).append(linha)

        for (nome_jogo, regiao), grupo in agrupado.items():
            fonte = FONTES_RANKING.get(grupo[0][2], grupo[0][2])
            partes.append(
                f"{nome_jogo} - ranking {regiao or 'global'} (fonte: {fonte}, "
                f"snapshot de {grupo[0][9]}):"
            )
            partes += [_descrever(linha) for linha in grupo[:por_bloco]]
        titulo = (
            "Ranking oficial do jogo citado" if codigos else "Ranking oficial por jogo"
        )

    if not partes:
        return None

    cabecalho = (
        "Ranking PUBLICADO pela fonte oficial de cada jogo - nao e medicao "
        "nossa, e nao e a mesma coisa que a forca estimada pelo nosso modelo "
        "(essa fica na aba Previsao). Diga a fonte e a data do snapshot."
    )
    return Bloco("ranking", titulo, cabecalho + "\n" + "\n".join(partes))


#: Brasil nao tem horario de verao desde 2019 - offset fixo, sem depender do
#: `tzdata` estar instalado na imagem do container.
FUSO_BRASILIA = timezone(timedelta(hours=-3))

GATILHOS_AGENDA = (
    "quando joga", "quando jogam", "quando vai jogar", "que horas joga",
    "proxima partida", "proximas partidas", "proximo jogo", "proximos jogos",
    "proximo confronto", "proximos confrontos", "agenda", "calendario",
    "tem jogo", "tem partida", "joga hoje", "jogam hoje", "vai jogar",
    "vao jogar", "joga quando", "jogam quando", "hoje", "amanha",
    "essa semana", "nesta semana",
    "ao vivo", "acontecendo agora", "rolando agora", "esta jogando",
)

#: Quanto tempo depois do horario marcado um confronto sem resultado ainda
#: conta como "deve estar rolando" (serie longa de MD5 passa de 3h).
JANELA_AO_VIVO = timedelta(hours=4)


def _quando_texto(momento: datetime, agora: datetime) -> str:
    """"hoje 16:00", "amanha 09:30" ou "sab 13/09 16:00" - sempre em Brasilia.

    O horario e o que a pessoa pergunta ("que horas joga?"), e o banco guarda
    em UTC. Sem a conversao aqui, a resposta sai 3 horas adiantada - errado de
    um jeito que parece certo, que e o pior tipo de erro para esta tela.
    """
    local = momento.astimezone(FUSO_BRASILIA)
    hoje = agora.astimezone(FUSO_BRASILIA).date()
    dias = (local.date() - hoje).days
    if dias == 0:
        prefixo = "hoje"
    elif dias == 1:
        prefixo = "amanha"
    elif dias == -1:
        prefixo = "ontem"
    else:
        prefixo = local.strftime("%d/%m")
    return f"{prefixo} {local:%H:%M} (horario de Brasilia)"


def _pede_agenda(pergunta: str) -> bool:
    normalizada = _normalizar(pergunta)
    return any(_normalizar(termo) in normalizada for termo in GATILHOS_AGENDA)


def _equipe_citada(pergunta: str, nomes: set[str], exato: bool = False) -> set[str]:
    """Quais dos nomes de equipe dados a pergunta cita.

    Casa o nome inteiro ("furia esports") ou uma palavra inteira dele com 4+
    letras ("furia" -> "FURIA Esports", "vitality" -> "Team Vitality"). O piso
    de 4 letras e o que evita "team", "the" e tag de 2 letras casarem com meia
    tabela - um falso positivo aqui nao e cosmetico: traz a agenda do time
    errado com cara de resposta.

    `exato=True` desliga o casamento por palavra e exige o nome inteiro. E o
    modo de quem NAO tem outro sinal na pergunta: "tem no game pass o Evil
    West?" casava "evil" com "Evil Geniuses" e trazia a agenda do time - uma
    pergunta de loja respondida com calendario de esports.
    """
    normalizada = _normalizar(pergunta)
    tokens = re.findall(r"[a-z0-9]+", normalizada)
    trechos = {
        " ".join(tokens[i:j])
        for i in range(len(tokens))
        for j in range(i + 1, min(i + 4, len(tokens)) + 1)
    }

    achados: set[str] = set()
    for nome in nomes:
        alvo = _normalizar(nome).strip()
        # Piso de 3 letras no NOME tambem, nao so na palavra: existe uma
        # equipe chamada "X" no banco, e sem isso ela casava com o "x" de
        # "FURIA x MIBR" - o separador virando um dos lados do confronto.
        if len(alvo) < 3:
            continue
        if alvo in trechos:
            achados.add(nome)
            continue
        if exato:
            continue
        palavras = [p for p in re.findall(r"[a-z0-9]+", alvo) if len(p) >= 4]
        if palavras and any(p in tokens for p in palavras):
            achados.add(nome)
    return achados


def _bloco_agenda(pergunta: str, sessao) -> Bloco | None:
    """Os proximos confrontos - do time citado, do jogo citado, ou de todos.

    E a pergunta mais comum de quem acompanha esports ("quando joga a
    FURIA?", "tem jogo hoje?") e a plataforma coleta exatamente isso na tela
    de Partidas - mas nenhum bloco trazia a agenda, entao o assistente
    respondia pela busca na web ou dizia que nao tinha. Tinha.

    Sem gatilho de tempo E sem time citado, devolve `None`: "quem venceu o
    mundial de 2023" nao e pergunta de agenda.
    """
    agora = datetime.now(timezone.utc)
    janela_passado = agora - timedelta(days=3)
    janela_futuro = agora + timedelta(days=14)

    linhas_agenda = sessao.execute(
        select(
            AgendaPartida.equipe_a_nome,
            AgendaPartida.equipe_b_nome,
            AgendaPartida.inicio_previsto,
            AgendaPartida.torneio,
            AgendaPartida.formato,
            AgendaPartida.vitoria_a,
            AgendaPartida.placar_a,
            AgendaPartida.placar_b,
            DimJogo.nome,
            DimJogo.codigo,
        )
        .join(DimJogo, DimJogo.id_jogo == AgendaPartida.id_jogo)
        .where(AgendaPartida.inicio_previsto.between(janela_passado, janela_futuro))
        .order_by(AgendaPartida.inicio_previsto)
    ).all()

    if not linhas_agenda:
        return None

    # O MESMO confronto chega por duas fontes (PandaScore e Liquipedia, por
    # exemplo) com o torneio escrito diferente. Listar os dois faz a resposta
    # dizer que o time joga duas vezes no mesmo horario - fica o de descricao
    # mais rica, que e o que tem o nome completo da fase.
    unicos: dict[tuple, Any] = {}
    for linha in linhas_agenda:
        chave = (
            linha[9],
            _normalizar(linha[0]),
            _normalizar(linha[1]),
            linha[2].replace(minute=0, second=0, microsecond=0),
        )
        atual = unicos.get(chave)
        if atual is None or len(linha[3] or "") > len(atual[3] or ""):
            unicos[chave] = linha
    linhas_agenda = sorted(unicos.values(), key=lambda linha: linha[2])

    nomes_em_jogo = {linha[0] for linha in linhas_agenda} | {
        linha[1] for linha in linhas_agenda
    }
    pede = _pede_agenda(pergunta)
    codigos_citados = _codigos_citados(pergunta)
    # Sem nenhuma palavra de agenda na pergunta, so o nome INTEIRO do time
    # conta - senao qualquer palavra de 4 letras que exista num nome de
    # equipe puxa o calendario para dentro de uma pergunta de loja.
    times_citados = _equipe_citada(pergunta, nomes_em_jogo, exato=not pede)

    if times_citados:
        alvo = [
            linha
            for linha in linhas_agenda
            if linha[0] in times_citados or linha[1] in times_citados
        ]
        titulo = f"Agenda de {', '.join(sorted(times_citados))}"
    elif codigos_citados and pede:
        alvo = [linha for linha in linhas_agenda if linha[9] in codigos_citados]
        titulo = "Agenda dos confrontos do jogo citado"
    elif pede:
        alvo = list(linhas_agenda)
        titulo = "Agenda de confrontos (todos os jogos)"
    else:
        return None

    if not alvo:
        return None

    futuros = [linha for linha in alvo if linha[2] > agora][:12]
    ao_vivo = [
        linha
        for linha in alvo
        if linha[5] is None and agora - JANELA_AO_VIVO <= linha[2] <= agora
    ][:6]
    decididos = [linha for linha in alvo if linha[5] is not None][-6:]

    linhas = [
        f"Agora sao {_quando_texto(agora, agora)}. A agenda vem da coleta "
        "(Liquipedia, PandaScore, vlr.gg e afins) - o horario pode mudar pela "
        "organizacao do torneio.",
    ]

    def _descrever(linha, com_placar: bool) -> str:
        a, b, inicio, torneio, formato, vitoria_a, placar_a, placar_b, jogo, _ = linha
        cabeca = f"{a} x {b} - {jogo}, {torneio or 'torneio nao informado'}"
        if formato:
            cabeca += f", {formato}"
        if com_placar and vitoria_a is not None:
            vencedor = a if vitoria_a else b
            placar = (
                f" {placar_a}-{placar_b}"
                if placar_a is not None and placar_b is not None
                else ""
            )
            return f"{cabeca}: venceu {vencedor}{placar} ({_quando_texto(inicio, agora)})"
        return f"{cabeca}: {_quando_texto(inicio, agora)}"

    if ao_vivo:
        linhas.append("")
        linhas.append("Deve estar em andamento agora (horario ja passou, sem resultado publicado):")
        linhas += [f"  {_descrever(linha, False)}" for linha in ao_vivo]

    if futuros:
        linhas.append("")
        linhas.append(f"Proximos confrontos ({len(futuros)} listados):")
        linhas += [f"  {_descrever(linha, False)}" for linha in futuros]
    else:
        linhas.append("")
        linhas.append(
            "Nenhum confronto FUTURO nesta janela de 14 dias para o que a "
            "pergunta pediu - diga isso, nao ofereca um confronto de outro time."
        )

    if decididos:
        linhas.append("")
        linhas.append("Resultados recentes (ultimos 3 dias):")
        linhas += [f"  {_descrever(linha, True)}" for linha in decididos]

    return Bloco("agenda", titulo, "\n".join(linhas))


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
    codigos_apelido = _codigos_citados(pergunta)
    jogos = sessao.execute(select(DimJogo.codigo, DimJogo.nome)).all()
    achados = [
        (codigo, nome)
        for codigo, nome in jogos
        if _normalizar(nome) in normalizada or codigo in codigos_apelido
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

    # Sem pontuacao dos dois lados: "Kaisa" na pergunta casa "Kai'Sa" no banco,
    # "belveth" casa "Bel'Veth". Mantem o espaco para "Twisted Fate" nao virar
    # substring solto.
    def _sem_pontuacao(texto: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", _normalizar(texto))

    pergunta_limpa = _sem_pontuacao(pergunta)

    candidatos = sessao.execute(
        select(DimPersonagem.nome, DimJogo.nome, DimPersonagem.metadados)
        .join(DimJogo, DimJogo.id_jogo == DimPersonagem.id_jogo)
        .where(DimPersonagem.metadados.has_key("guia"))
        # Nomes mais longos primeiro: "Twisted Fate" antes de "Fate", se
        # existisse.
        .order_by(func.length(DimPersonagem.nome).desc())
    ).all()

    alvo = None
    for nome_p, nome_jogo, metadados in candidatos:
        # `\b` dos dois lados: "Mel" nao casa dentro de "melhor", mas casa
        # sozinho; "Twisted Fate" casa como frase.
        if re.search(rf"\b{re.escape(_sem_pontuacao(nome_p))}\b", pergunta_limpa):
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


#: Abaixo disso o percentual de um jogo e ruido (1 avaliacao negativa vira
#: "0% positivas" e dispara o extremo por um caso isolado).
RECEPCAO_MIN_AVALIACOES = 5


def _bloco_sentimento(pergunta: str, sessao) -> tuple[Bloco, SerieAssistente]:
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

    # A lista/grafico por padrao mostra os MAIS avaliados (por volume) - uma
    # visao geral razoavel. Mas quando a pergunta pede o PIOR/MELHOR do nosso
    # catalogo, o grafico tem que mostrar essa ponta (ordenado por
    # percentual), senao ele mostra "os mais avaliados" enquanto o texto (que
    # le a lista inteira) responde o jogo com a nota mais baixa/alta de fato -
    # o grafico contradizendo a resposta.
    extremo = _extremo_recepcao_pedido(pergunta)
    elegiveis = [linha for linha in por_jogo if linha[1] >= RECEPCAO_MIN_AVALIACOES] or list(por_jogo)
    if extremo == "pior":
        ordenado = sorted(elegiveis, key=lambda linha: float(linha[2] or 0) / linha[1])
        titulo_serie = "Pior recepção (coletada)"
    elif extremo == "melhor":
        ordenado = sorted(elegiveis, key=lambda linha: float(linha[2] or 0) / linha[1], reverse=True)
        titulo_serie = "Melhor recepção (coletada)"
    else:
        ordenado = por_jogo
        titulo_serie = "Avaliações positivas por jogo (coletadas)"

    serie = SerieAssistente(
        chave="sentimento",
        titulo=titulo_serie,
        unidade="%",
        itens=[
            PontoSerie(
                rotulo=nome,
                valor=round(100 * float(pos or 0) / total, 1),
                detalhe=f"{total} avaliações",
            )
            for nome, total, pos in ordenado[:8]
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
    # "jogo"/"jogos" NAO entram aqui de proposito: sao palavras genericas
    # demais (quase toda pergunta do dominio tem uma delas), e casar com elas
    # fazia o catalogo INTEIRO da Steam - ordenado por jogadores simultaneos -
    # entrar em quase toda resposta, mesmo perguntas sobre um jogo especifico
    # que nao esta no nosso catalogo (ex.: "me fala sobre o jogo Diablo IV").
    # O gatilho real tem que ser sobre O CATALOGO em si (preco, genero,
    # desconto, "quais jogos vocês tem") - nao qualquer mencao a "jogo".
    "steam": ("steam", "preco", "preço", "catalogo", "catálogo",
              "jogadores simultaneos", "ccu", "genero", "gênero", "desconto",
              "quais jogos", "que jogos"),
    "partidas": ("partida", "partidas", "dota", "torneio", "liga", "duracao",
                 "duração", "radiant", "dire", "esport"),
    "herois": ("heroi", "herói", "herois", "heróis", "winrate", "personagem", "meta",
               "agente", "agentes", "campeao", "campeão", "campeoes", "campeões",
               "pick rate", "taxa de escolha", "tier"),
    "modelos": ("modelo", "modelos", "previsao", "previsão", "prever", "acuracia",
                "acurácia", "roc", "auc", "treino", "machine learning", "ml",
                "confronto", "confrontos", "quem ganha", "quem vence", "favorito"),
    "sentimento": ("sentimento", "avaliacao", "avaliação", "avaliacoes", "avaliações",
                   "review", "reviews", "positiva", "negativa", "nlp"),
    # Sem construtor no laco de `montar_contexto` (o bloco de guia se monta
    # sozinho); serve para marcar a pergunta como "e da nossa base" e nao
    # disparar a busca na web a toa.
    "guia": ("build", "buildar", "buildo", "itemizacao", "itens do", "montar no",
             "ordem de habilidade", "ordem de skill", "upar", "runa", "runas",
             "feitico de invocador", "como jogar", "como jogo de"),
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
    #: `True` quando nenhum bloco NOSSO respondeu uma pergunta do mundo dos
    #: jogos - `perguntar` entao libera a busca na web do OpenRouter.
    web_sugerida: bool = False
    #: `True` quando a pergunta e do mundo dos jogos/esports. `False` recusa a
    #: pergunta (fora do escopo) e nao deixa a web buscar.
    no_dominio: bool = True


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
    }

    # Os gatilhos que a pergunta casou DE VERDADE, e so eles. O GRAFICO de um
    # bloco tambem so sobe com gatilho explicito - senao "como buildar a
    # Kaisa" mostraria o grafico de jogadores da Steam ao lado da resposta.
    #
    # Existia aqui um fallback de "nada casou -> entram todos os blocos, para
    # o modelo ter o que ler". Ele saiu: hoje `plataforma` e `geral` entram
    # SEMPRE (o que a plataforma faz, e os volumes de cada base), e os blocos
    # que respondem sozinhos - agenda, ranking, xbox, Steam ao vivo, loja,
    # elenco, guia, previsao - tem gatilho proprio, independente deste mapa.
    # O que o fallback fazia, na pratica, era despejar winrate de heroi de
    # Dota em pergunta que nao pedia nada disso.
    gatilhos_explicitos = {
        chave
        for chave, termos in GATILHOS.items()
        if any(_normalizar(termo) in normalizada for termo in termos)
    }
    escolhidos = gatilhos_explicitos

    with session_scope() as sessao:
        blocos = [_bloco_plataforma(sessao), _bloco_geral(sessao)]
        series: list[SerieAssistente] = []
        for chave in ("steam", "partidas", "herois", "sentimento"):
            if chave in escolhidos:
                if chave == "sentimento":
                    bloco, serie = _bloco_sentimento(pergunta, sessao)
                else:
                    bloco, serie = construtores[chave](sessao)
                blocos.append(bloco)
                if (
                    serie is not None
                    and serie.itens
                    and chave in gatilhos_explicitos
                ):
                    series.append(serie)

        # Independe de gatilho de categoria: citar o nome de um time ja basta
        # ("quando joga a FURIA?" nao tem palavra de agenda nenhuma se a
        # pessoa escrever so "FURIA joga quando").
        agenda = _bloco_agenda(pergunta, sessao)
        if agenda is not None:
            blocos.append(agenda)

        ranking = _bloco_ranking(pergunta, sessao)
        if ranking is not None:
            blocos.append(ranking)

        xbox = _bloco_xbox(pergunta, sessao)
        if xbox is not None:
            blocos.append(xbox)

        online, serie_online = _bloco_steam_online(pergunta, sessao)
        if online is not None:
            blocos.append(online)
            if serie_online is not None and serie_online.itens:
                # Na FRENTE: quem pergunta "qual o mais jogado agora" quer o
                # grafico da Steam inteira. O do nosso catalogo ao lado dessa
                # resposta mostraria outros numeros para a mesma pergunta.
                series.insert(0, serie_online)

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
            # Uma build nao e grandeza que caiba num grafico. Se a serie do
            # topo veio de um bloco que so entrou pelo fallback (nao e da
            # pergunta), ela some - melhor sem grafico do que com um alheio.
            if series and series[0].chave not in gatilhos_explicitos | {"elenco"}:
                series = []

        # Antes do bloco de modelos de proposito: quando a pergunta nomeia dois
        # times, a resposta e a previsao DELES; as metricas do modelo entram
        # como contexto de quanto confiar, nao como a resposta.
        previsao = _bloco_previsao(pergunta, sessao)
        if previsao is not None:
            blocos.append(previsao)

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

    blocos = [bloco for bloco in blocos if bloco.conteudo.strip()]

    # Web: quando a nossa base nao respondeu de fato. Um bloco que fecha a
    # pergunta (jogo identificado na loja, recomendacao, extremo de avaliacao)
    # ja e resposta - nao busca. `elenco` e `guia` NAO contam aqui: eles
    # disparam so por citar um jogo ou personagem, e "quem venceu o mundial de
    # LoL" traz o bloco de elenco sem responder nada. Dai o filtro real e o
    # gatilho: se nenhuma palavra da nossa base casou (ou a pergunta pediu a
    # web na cara), a web entra.
    fecha_a_pergunta = any(
        b.chave in ("descoberta", "recomendacao", "extremo_avaliacao")
        for b in blocos
    )
    web_sugerida = not fecha_a_pergunta

    # Escopo: a pergunta e do mundo dos jogos? Sim se um gatilho nosso casou, se
    # um bloco que so entra por NOME DE JOGO/PERSONAGEM apareceu, se ela cita um
    # jogo do banco, ou se tem vocabulario do dominio. (Recomendacao NAO conta:
    # "recomenda um livro" dispara o mesmo caminho de "recomenda um jogo".)
    blocos_de_jogo = any(
        b.chave in ("steam_ao_vivo", "elenco", "guia")
        for b in blocos
    )
    # `\b` dos dois lados: "br" nao casa dentro de "sobre", "meta" nao casa em
    # "cometa" - mas "esports?" e "meta." casam.
    tem_vocabulario = any(
        re.search(rf"\b{re.escape(_normalizar(t))}\b", normalizada)
        for t in TERMOS_DOMINIO
    )
    no_dominio = bool(
        gatilhos_explicitos
        or blocos_de_jogo
        or jogo_ao_vivo is not None
        or _codigos_citados(pergunta)
        or tem_vocabulario
    )

    return ContextoMontado(
        blocos=blocos,
        recomendacoes=recomendacoes,
        jogo_ao_vivo=jogo_ao_vivo,
        series=series,
        web_sugerida=web_sugerida,
        no_dominio=no_dominio,
    )


#: Vocabulario que marca a pergunta como sendo do mundo dos jogos/esports - o
#: unico assunto que este assistente cobre. Fora disso ele recusa, e a busca na
#: web NAO dispara (senao "qual o pior rei da Espanha" viraria uma aula de
#: historia). Lista ampla de proposito: e melhor deixar passar uma pergunta de
#: jogo obscura do que responder sobre qualquer coisa.
TERMOS_DOMINIO = (
    "jogo", "jogos", "game", "gamer", "gaming", "videogame", "steam", "epic",
    "console", "pc gamer", "playstation", "xbox", "nintendo", "switch",
    "esport", "esports", "e-sport", "torneio", "campeonato", "mundial", "major",
    "liga", "playoff", "bracket", "chave", "confronto", "partida", "partidas",
    "scrim", "lan", "meta", "patch", "atualizacao do jogo", "nerf", "buff",
    "heroi", "herói", "campeao", "campeão", "agente", "personagem", "build",
    "itemizacao", "runa", "skin", "elo", "rank", "ranqueada", "matchmaking",
    "dota", "valorant", "lol", "league of legends", "counter", "cs2", "csgo",
    "fps", "moba", "rpg", "battle royale", "br", "mmorpg", "tft", "wild rift",
    "riot", "valve", "blizzard", "steam deck", "twitch", "streamer", "speedrun",
    "dlc", "early access", "beta", "review", "avaliacao", "preco do jogo",
    "lancamento", "gameplay", "campanha", "modo online", "multiplayer",
    "co-op", "coop", "pvp", "pve", "raid", "boss", "loot", "grind",
    "plataforma", "nosso sistema", "nosso site", "nosso banco", "dashboard",
    # Perguntar sobre o PROPRIO site e do escopo - "o que esse site faz?"
    # caia em FORA_ESCOPO, que e a pior resposta possivel para a pergunta
    # que o bloco da plataforma existe para responder.
    "site", "playdb", "sistema", "app", "aplicativo", "tela", "telas", "aba",
    "menu", "pagina", "rota",
    "coleta", "modelo de previsao", "winrate", "pick rate", "kda",
    "jogador", "jogadora", "pro player", "proplayer", "pro-player", "atleta",
    "roster", "escalacao", "midlane", "toplane", "jungle", "jungler", "adc",
    "carry", "igl", "draft", "clutch", "headshot", "legends", "worlds",
    "lck", "lpl", "lcs", "lec", "cblol", "esl", "iem", "blast", "invitational",
    "the international",
    # O que o site faz e como se pergunta por isso - sem estes termos, "tem
    # jogo hoje?" e "tem no game pass?" eram julgadas fora do escopo.
    "game pass", "gamepass", "microsoft store", "series x", "series s",
    "agenda", "calendario", "proxima partida", "proximo jogo", "quando joga",
    "ao vivo", "ranking", "classificacao", "standings", "favorito",
    "promocao", "desconto", "favoritar", "favoritos", "assistente",
    "catalogo", "loja", "perfil", "conta", "apk",
)


#: A pergunta pede a web explicitamente - a busca ja vai na primeira tentativa,
#: sem esperar a primeira resposta "nao tenho isso".
TERMOS_WEB = (
    "pesquisa na web", "busca na web", "pesquise na web", "busque na web",
    "na internet", "pesquisa na internet", "procura na internet", "procure na internet",
    "pesquise online", "busca online", "pesquisar online", "search",
)


def _pede_web(pergunta: str) -> bool:
    normalizada = _normalizar(pergunta)
    return any(_normalizar(t) in normalizada for t in TERMOS_WEB)


#: O sinal que o modelo emite (regra 16) quando o CONTEXTO nao responde e a web
#: resolveria. `perguntar` intercepta e refaz a chamada com a busca ligada.
SINAL_WEB = "PRECISA_WEB"

#: O sinal da regra 0: a pergunta nao e do mundo dos jogos.
SINAL_FORA = "FORA_ESCOPO"


def _fora_escopo(texto: str) -> bool:
    """`True` quando a resposta e so o sinal de fora do escopo (regra 0).

    Curta de proposito: uma resposta longa que por acaso cita "fora do escopo"
    no meio ja e uma resposta de verdade.
    """
    limpo = (texto or "").strip()
    return SINAL_FORA in limpo.upper() and len(limpo) < 120

#: Rede de seguranca: se o modelo nao emitiu o sinal mas a resposta curta e so
#: uma recusa, tambem vale como "sem resposta".
_RECUSA = re.compile(
    r"fora dos dados"
    r"|n[aã]o (?:d[aá] pra?|temos|tenho|h[aá]|consigo|e poss[ií]vel|foi poss[ií]vel|"
    r"cobre|aparece|consta|est[aá] no|encontr)"
    r"|(?:nenhum|nao ha fonte)[^.!?:]*\bcobre"
    r"|falta(?:m)? (?:esse|este|o |a |dados?|informa)"
    r"|sem (?:esse|esses|o |os )?dados?",
    re.I,
)


def _parece_sem_resposta(texto: str) -> bool:
    limpo = (texto or "").strip()
    if SINAL_WEB in limpo.upper():
        return True
    # Sem o sinal, so conta se a resposta e curta E abre com a recusa - uma
    # resposta longa com ressalva no fim ja respondeu.
    if len(limpo) > 320:
        return False
    primeira = re.split(r"(?<=[.!?:])\s", limpo, maxsplit=1)[0]
    return bool(_RECUSA.search(primeira))


def _chamar_modelo(corpo: dict[str, Any], settings) -> dict[str, Any]:
    """Um POST ao OpenRouter. Devolve `{texto, annotations, modelo, uso}`.

    Toda saida (sucesso ou falha) passa por `telemetria_assistente.registrar` -
    e o que alimenta o painel "Status da API" da tela do assistente, pra um
    429 do provedor aparecer como "modelo gratis limitado agora" em vez de
    parecer bug nosso.
    """
    inicio = time.monotonic()
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
        telemetria_assistente.registrar(
            sucesso=False,
            status_http=None,
            erro=f"{type(exc).__name__}: {exc}",
            duracao_ms=round((time.monotonic() - inicio) * 1000),
        )
        raise AssistenteIndisponivel(
            f"nao foi possivel falar com o OpenRouter: {type(exc).__name__}"
        ) from exc

    duracao_ms = round((time.monotonic() - inicio) * 1000)

    if resposta.status_code != 200:
        telemetria_assistente.registrar(
            sucesso=False,
            status_http=resposta.status_code,
            erro=resposta.text[:200],
            duracao_ms=duracao_ms,
        )
        raise AssistenteIndisponivel(
            f"OpenRouter respondeu {resposta.status_code}: {resposta.text[:200]}"
        )
    dados = resposta.json()
    if "error" in dados:
        telemetria_assistente.registrar(
            sucesso=False,
            status_http=resposta.status_code,
            erro=str(dados["error"])[:200],
            duracao_ms=duracao_ms,
        )
        raise AssistenteIndisponivel(str(dados["error"])[:200])

    telemetria_assistente.registrar(
        sucesso=True,
        status_http=resposta.status_code,
        erro=None,
        duracao_ms=duracao_ms,
    )
    mensagem = ((dados.get("choices") or [{}])[0].get("message")) or {}
    return {
        "texto": (mensagem.get("content") or "").strip(),
        "annotations": mensagem.get("annotations"),
        "modelo": dados.get("model") or settings.openrouter_model,
        "uso": dados.get("usage") or {},
    }


#: Modelo usado quando a conta escolheu Anthropic/Google mas nao disse qual -
#: um atual e equilibrado (nem o mais caro, nem o mais fraco), ja que quem
#: paga a conta e a propria pessoa. No OpenRouter o padrao continua sendo o
#: `settings.openrouter_model` do site (ele ja da acesso a Claude/Gemini por
#: tras da mesma chave - so nao escolhia o modelo antes da Fase 34).
_MODELO_PADRAO_DIRETO = {
    "anthropic": "claude-sonnet-5",
    "google": "gemini-3.8-flash",
}


def _chamar_anthropic(
    texto_usuario: str, sistema: str, modelo: str, api_key: str
) -> dict[str, Any]:
    """Chave direta da Anthropic (Fase 34) - via SDK oficial (`pip install
    anthropic`), nao REST cru: o SDK ja tipa os erros (chave invalida, rate
    limit, conexao) em vez de forcar reparsear corpo de erro feito a mao.

    Sem telemetria (`telemetria_assistente`) aqui de proposito: aquele painel
    e sobre a SAUDE DA CHAVE COMPARTILHADA do site, nao da chave pessoal de
    quem esta perguntando - misturar os dois faria uma chave de terceiro
    falhando aparecer como se fosse a nossa.
    """
    import anthropic

    cliente = anthropic.Anthropic(api_key=api_key)
    try:
        resposta = cliente.messages.create(
            model=modelo,
            max_tokens=700,
            temperature=0.2,
            system=sistema,
            messages=[{"role": "user", "content": texto_usuario}],
        )
    except anthropic.AuthenticationError as exc:
        raise AssistenteIndisponivel(
            "a Anthropic recusou a chave (invalida ou sem credito)"
        ) from exc
    except anthropic.APIStatusError as exc:
        raise AssistenteIndisponivel(
            f"Anthropic respondeu {exc.status_code}: {str(exc)[:200]}"
        ) from exc
    except anthropic.APIConnectionError as exc:
        raise AssistenteIndisponivel(
            f"nao foi possivel falar com a Anthropic: {type(exc).__name__}"
        ) from exc

    texto = "".join(
        bloco.text for bloco in resposta.content if getattr(bloco, "type", None) == "text"
    ).strip()

    return {
        "texto": texto,
        "annotations": None,
        "modelo": resposta.model,
        "uso": {
            "prompt_tokens": resposta.usage.input_tokens,
            "completion_tokens": resposta.usage.output_tokens,
        },
    }


def _chamar_google(
    texto_usuario: str, sistema: str, modelo: str, api_key: str, timeout_segundos: float
) -> dict[str, Any]:
    """Chave direta do Google AI Studio (Fase 34) - REST cru, no mesmo estilo
    do resto do projeto (`_chamar_modelo` acima). A chave vai na query
    string (`?key=`) - e assim que a API do Gemini pede, nao num header."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    try:
        resposta = requests.post(
            url,
            params={"key": api_key},
            json={
                "contents": [{"role": "user", "parts": [{"text": texto_usuario}]}],
                "systemInstruction": {"parts": [{"text": sistema}]},
                "generationConfig": {"maxOutputTokens": 700, "temperature": 0.2},
            },
            timeout=timeout_segundos,
        )
    except requests.RequestException as exc:
        raise AssistenteIndisponivel(
            f"nao foi possivel falar com o Google: {type(exc).__name__}"
        ) from exc

    if resposta.status_code != 200:
        raise AssistenteIndisponivel(
            f"Google respondeu {resposta.status_code}: {resposta.text[:200]}"
        )
    dados = resposta.json()
    if "error" in dados:
        raise AssistenteIndisponivel(str(dados["error"])[:200])

    candidatos = dados.get("candidates") or []
    partes = ((candidatos[0].get("content") or {}).get("parts") if candidatos else None) or []
    texto = "".join(p.get("text", "") for p in partes).strip()
    uso_bruto = dados.get("usageMetadata") or {}

    return {
        "texto": texto,
        "annotations": None,
        "modelo": modelo,
        "uso": {
            "prompt_tokens": uso_bruto.get("promptTokenCount"),
            "completion_tokens": uso_bruto.get("candidatesTokenCount"),
        },
    }


# ---------------------------------------------------------------------------
# Chamada ao provedor
# ---------------------------------------------------------------------------


def perguntar(
    pergunta: str,
    chave_pessoal: str | None = None,
    provedor_pessoal: str | None = None,
    modelo_pessoal: str | None = None,
) -> Resposta:
    """Monta o contexto, chama o modelo e devolve resposta + contexto usado.

    `chave_pessoal`: chave de IA da propria conta (Fase 33/34), ja decifrada
    por quem chamou. `provedor_pessoal` diz qual API ela abre
    ("openrouter"/"anthropic"/"google" - "openrouter" se omitido, por
    compatibilidade). No OpenRouter, a chave (e o `modelo_pessoal`, se
    dado) substituem os do site so nesta chamada, via copia de `settings` -
    o `.env`/processo nunca muda. Anthropic e Google sao chamados direto
    (`_chamar_anthropic`/`_chamar_google`), sem passar pelo OpenRouter.

    O modo web (busca ao vivo, `PRECISA_WEB`) so existe no caminho OpenRouter
    - e um plugin dele, sem equivalente pronto nos outros dois. Perguntando
    com chave da Anthropic/Google, uma pergunta que precisaria da web cai na
    mesma mensagem de "nao consegui completar" que o site ja mostra com o
    modo web desligado.
    """
    settings = get_settings()
    provedor = (provedor_pessoal or "openrouter") if chave_pessoal else "openrouter"
    usando_direto = chave_pessoal is not None and provedor != "openrouter"

    if chave_pessoal and provedor == "openrouter":
        settings = settings.model_copy(
            update={
                "openrouter_api_key": chave_pessoal,
                **({"openrouter_model": modelo_pessoal} if modelo_pessoal else {}),
            }
        )
    if provedor == "openrouter" and not settings.openrouter_api_key:
        raise AssistenteIndisponivel(
            "OPENROUTER_API_KEY nao configurada. Defina no .env para usar o assistente."
        )

    modelo_efetivo = (
        settings.openrouter_model
        if provedor == "openrouter"
        else (modelo_pessoal or _MODELO_PADRAO_DIRETO[provedor])
    )

    contexto_montado = montar_contexto(pergunta)
    blocos = contexto_montado.blocos

    def _fora_do_escopo() -> Resposta:
        return Resposta(
            pergunta=pergunta,
            resposta=(
                "Só respondo sobre o mundo dos jogos e esports - essa pergunta "
                "está fora do que o PlayDB cobre."
            ),
            modelo=modelo_efetivo,
            blocos=[b for b in blocos if b.chave == "geral"],
            usando_chave_propria=bool(chave_pessoal),
            provedor_ia=provedor if chave_pessoal else None,
        )

    contexto = "\n\n".join(
        f"### {bloco.titulo}\n{bloco.conteudo}" for bloco in blocos
    )

    def _corpo(mensagem_extra: str = "") -> dict[str, Any]:
        return {
            "model": settings.openrouter_model,
            "max_tokens": 700,
            # Temperatura baixa: a tarefa e reproduzir numeros do contexto, nao
            # variar a redacao. Criatividade aqui so aumenta a chance de inventar.
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": INSTRUCAO},
                {
                    "role": "user",
                    "content": (
                        f"CONTEXTO:\n{contexto}\n\nPERGUNTA: {pergunta}"
                        + mensagem_extra
                    ),
                },
            ],
        }

    # A chamada da web leva SO a pergunta na mensagem do usuario: a query da
    # busca do OpenRouter sai dai, e mandar a ficha de Steam/Dota (ou ate o
    # mapa de capacidade, cheio de "Liquipedia", "OP.GG", "esports") junto
    # sujava a busca - voltavam repositorios de analytics em vez da resposta.
    # O que a nossa base tem vai no system, para o modelo situar sem poluir a
    # busca.
    def _corpo_web() -> dict[str, Any]:
        return {
            "model": settings.openrouter_model,
            "max_tokens": 700,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        INSTRUCAO
                        + "\n\nMODO WEB: a nossa base nao respondeu esta "
                        "pergunta. Responda pelos resultados da web, citando a "
                        "fonte (site/pagina) de cada afirmacao. Se a web nao "
                        "trouxer, use a regra 3."
                    ),
                },
                {"role": "user", "content": pergunta},
            ],
            # O plugin `web`: o OpenRouter busca, injeta os resultados e devolve
            # as citacoes em `annotations`. O modelo nao escolhe buscar - o
            # Python decidiu, pelo motivo de sempre (`collectors/opgg_mcp`).
            "plugins": [
                {"id": "web", "max_results": settings.assistente_web_max_resultados}
            ],
        }

    def _chamar(corpo_openrouter: dict[str, Any]) -> dict[str, Any]:
        """Despacha pro provedor certo. `corpo_openrouter` sempre existe (o
        caminho OpenRouter usa ele direto); Anthropic/Google so aproveitam o
        `system`/`user` ja montados dentro dele - nao repetem a formatacao
        do CONTEXTO."""
        if provedor == "openrouter":
            return _chamar_modelo(corpo_openrouter, settings)
        mensagens = corpo_openrouter["messages"]
        sistema = mensagens[0]["content"]
        texto_usuario = mensagens[1]["content"]
        if provedor == "anthropic":
            return _chamar_anthropic(texto_usuario, sistema, modelo_efetivo, chave_pessoal)
        if provedor == "google":
            return _chamar_google(
                texto_usuario,
                sistema,
                modelo_efetivo,
                chave_pessoal,
                settings.openrouter_timeout_seconds,
            )
        raise AssistenteIndisponivel(f"provedor de IA desconhecido: {provedor}")  # pragma: no cover

    # A busca ja na primeira chamada so quando a pergunta pede na cara ("pesquisa
    # na web ...") E o filtro de palavras nao a marcou como claramente fora do
    # mundo dos jogos. So existe no OpenRouter (ver docstring) - `usando_direto`
    # desliga o modo web inteiro pras chamadas diretas.
    web_ligada = settings.assistente_web_habilitada and not usando_direto
    web_na_primeira = (
        web_ligada
        and contexto_montado.web_sugerida
        and contexto_montado.no_dominio
        and _pede_web(pergunta)
    )

    usou_web = web_na_primeira
    saida = _chamar(_corpo_web() if web_na_primeira else _corpo())

    # Escopo: o modelo (regra 0) responde `FORA_ESCOPO` quando a pergunta nao e
    # do mundo dos jogos. E ele o juiz - o filtro de palavras erra ("Legue of
    # Legends" com erro de digitacao passava batido).
    if _fora_escopo(saida["texto"]):
        return _fora_do_escopo()

    # Segunda tentativa COM a busca, quando a primeira nao achou (o modelo pede
    # com `PRECISA_WEB`, ou a resposta curta e so uma recusa). So aqui - assim a
    # maioria das perguntas (que a base responde) custa uma chamada, sem busca.
    if (
        web_ligada
        and contexto_montado.web_sugerida
        and not web_na_primeira
        and _parece_sem_resposta(saida["texto"])
    ):
        segunda = _chamar(_corpo_web())
        if segunda["texto"] and not _fora_escopo(segunda["texto"]):
            saida = segunda
            usou_web = True

    # O sinal `PRECISA_WEB` nao pode vazar para a tela (a web nao respondeu, ou
    # esta desligada) - vira a recusa normal.
    texto = saida["texto"]
    if SINAL_WEB in texto.upper():
        texto = (
            "Não tenho esse dado no nosso banco e não consegui completar com a "
            "busca na web agora. Tente reformular ou consulte a fonte oficial "
            "do jogo/torneio."
        )
        usou_web = False

    if not texto:
        raise AssistenteIndisponivel("o modelo devolveu resposta vazia")

    fontes_web = _fontes_da_web(saida["annotations"])
    if fontes_web:
        linhas = [
            "Estas paginas o OpenRouter buscou na web AGORA para esta pergunta. "
            "Nao sao medicao nossa. A resposta cita a fonte de cada afirmacao:",
        ]
        linhas += [f"- {f['titulo']} ({f['url']})" for f in fontes_web]
        blocos = [
            *blocos,
            Bloco("web", "Busca na web (resultado externo)", "\n".join(linhas), fonte="web"),
        ]

    # A resposta veio da web: o grafico dos NOSSOS blocos (pick rate de campeao,
    # etc.) nao e sobre ela - fora.
    series = [] if usou_web else contexto_montado.series

    uso = saida["uso"]
    return Resposta(
        pergunta=pergunta,
        resposta=texto,
        modelo=saida["modelo"],
        blocos=blocos,
        recomendacoes=contexto_montado.recomendacoes,
        jogo_ao_vivo=contexto_montado.jogo_ao_vivo,
        series=series,
        fontes_web=fontes_web,
        tokens_entrada=uso.get("prompt_tokens"),
        tokens_saida=uso.get("completion_tokens"),
        usando_chave_propria=bool(chave_pessoal),
        provedor_ia=provedor if chave_pessoal else None,
    )


def _fontes_da_web(annotations: Any) -> list[dict[str, str]]:
    """As citacoes `url_citation` da resposta do OpenRouter, sem repetir URL."""
    if not isinstance(annotations, list):
        return []
    vistos: set[str] = set()
    fontes: list[dict[str, str]] = []
    for anotacao in annotations:
        if not isinstance(anotacao, dict) or anotacao.get("type") != "url_citation":
            continue
        cit = anotacao.get("url_citation") or {}
        url = cit.get("url")
        if not isinstance(url, str) or url in vistos:
            continue
        vistos.add(url)
        fontes.append({"url": url, "titulo": cit.get("title") or url})
    return fontes
