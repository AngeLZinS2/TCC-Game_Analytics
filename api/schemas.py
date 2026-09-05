"""Modelos de resposta da API.

Sao o contrato com o frontend: mudanca aqui quebra o dashboard, entao os nomes
seguem o dominio (portugues, como o banco) em vez de espelhar o SQL bruto.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from decimal import Decimal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


class ColetaFonte(BaseModel):
    fonte: str
    payloads: int
    ultima_coleta: datetime | None


class VisaoGeral(BaseModel):
    """KPIs da home do dashboard: um numero por dominio."""

    jogos_steam: int
    snapshots_steam: int
    jogadores_simultaneos_total: int | None
    partidas: int
    linhas_fato_partida: int
    jogadores: int
    personagens: int
    coletas: list[ColetaFonte]


# ---------------------------------------------------------------------------
# Steam
# ---------------------------------------------------------------------------


class JogoSteam(BaseModel):
    """Dimensao + o snapshot mais recente, achatados para a tabela do dashboard."""

    app_id: int
    nome: str
    desenvolvedora: str | None
    publicadora: str | None
    data_lancamento: date | None
    generos: list[str]
    gratuito: bool | None
    nota_metacritic: int | None

    janela_coleta: datetime | None
    jogadores_simultaneos: int | None
    nota_avaliacoes: Decimal | None
    numero_avaliacoes: int | None
    classificacao_steam: str | None
    preco_no_momento: Decimal | None
    moeda: str | None
    desconto_percentual: int | None

    #: A capa real, da Steam. Vem na LISTA (e nao so na ficha) porque a
    #: Valve migrou os jogos novos pra um caminho com hash: o palpite
    #: deterministico de CDN da 404 em 6 dos nossos 27, e a linha ficava
    #: com a inicial do nome no lugar da capa. E um campo so, nao a ficha.
    imagem_header: str | None = None

    #: Maior valor ja coletado para este jogo.
    pico_jogadores: int | None = None
    #: Variacao percentual sobre a coleta anterior. None enquanto so houver uma.
    variacao_jogadores: float | None = None


class PontoSerie(BaseModel):
    """Um ponto da serie temporal de um jogo."""

    janela_coleta: datetime
    jogadores_simultaneos: int | None
    nota_avaliacoes: Decimal | None
    numero_avaliacoes: int | None
    preco_no_momento: Decimal | None
    desconto_percentual: int | None


class PontoSerieTotal(BaseModel):
    """Um ponto da serie agregada do catalogo inteiro."""

    janela_coleta: datetime
    jogadores_simultaneos: int | None
    jogos: int


class ConquistaDestaque(BaseModel):
    nome: str
    icone: str


class MidiaJogo(BaseModel):
    """Um item da galeria da loja: um trailer ou uma captura de tela.

    `tipo` decide como a tela mostra: `video` toca (HLS, mudo, e passa pro
    proximo quando acaba), `imagem` fica alguns segundos e troca.
    """

    tipo: str
    url: str
    #: So no video: o frame de capa, exibido enquanto o player nao comeca.
    cartaz: str = ""
    titulo: str = ""


class FichaJogoSteam(BaseModel):
    """Metadados do jogo que quase nao mudam - a "ficha" estilo SteamDB.

    Fica fora de `JogoSteam` (a linha da tabela) de proposito: sao ~20 campos
    que so a tela de detalhe usa, e carregar isso em cada linha da lista de
    jogos seria peso morto.
    """

    tipo: str | None = None
    recursos: list[str] = []
    plataformas: list[str] = []
    idiomas: list[str] = []
    idiomas_com_audio: list[str] = []
    faixa_etaria: int | None = None
    descritores_conteudo: list[str] = []
    classificacoes: dict[str, str] = {}
    suporte_controle: str | None = None
    conquistas_total: int | None = None
    conquistas_destaque: list[ConquistaDestaque] = []
    analises_totais: int | None = None
    dlc_ids: list[int] = []
    site_oficial: str | None = None
    imagem_header: str | None = None
    em_breve: bool | None = None
    requisitos_minimos: str | None = None
    #: Nulo quando o jogo nao publica recomendado - a tela some com a aba.
    requisitos_recomendados: str | None = None
    #: Trailers e capturas da pagina da loja, na ordem do carrossel do topo
    #: da ficha. Video vem em HLS (a Steam nao publica mais mp4/webm direto).
    midias: list[MidiaJogo] = []
    #: SteamSpy - faixa, nunca numero exato.
    donos_estimados: str | None = None
    tempo_jogo_medio_min: int | None = None
    tempo_jogo_mediano_min: int | None = None
    #: {tag: votos}, ja ordenado por votos desc.
    tags_comunidade: list[tuple[str, int]] = []
    coletado_ficha_em: datetime | None = None

    #: HowLongToBeat - tempo estimado pra zerar. Casado por NOME (Steam e
    #: HLTB nao compartilham id), por isso `hltb_nome` vem junto: confere se
    #: o casamento achou o jogo certo. `None` em tudo = ainda nao coletado ou
    #: nenhum candidato bateu com confianca suficiente.
    hltb_id: str | None = None
    hltb_nome: str | None = None
    hltb_horas_historia: Decimal | None = None
    hltb_horas_extras: Decimal | None = None
    hltb_horas_completista: Decimal | None = None
    coletado_tempo_em: datetime | None = None


class NoticiaSteam(BaseModel):
    gid: str
    titulo: str
    url: str | None
    autor: str | None
    feed: str | None
    publicado_em: datetime | None
    resumo: str | None


class OfertaLoja(BaseModel):
    """Preco de um jogo numa loja, via IsThereAnyDeal."""

    loja: str
    preco: Decimal
    preco_normal: Decimal | None
    desconto: int | None
    moeda: str | None
    url: str | None
    drm: str | None
    #: `True` na loja mais barata da lista.
    melhor: bool = False


class MenorPrecoHistorico(BaseModel):
    preco: Decimal
    loja: str | None
    moeda: str | None
    data: date | None


class DetalheJogoSteam(BaseModel):
    jogo: JogoSteam
    ficha: FichaJogoSteam
    noticias: list[NoticiaSteam] = []
    #: Ofertas em outras lojas, da mais barata para a mais cara. Vazio para
    #: jogo gratuito ou quando o ITAD nao conhece o jogo (ou sem `ITAD_API_KEY`).
    ofertas: list[OfertaLoja] = []
    menor_preco_historico: MenorPrecoHistorico | None = None
    serie: list[PontoSerie]


class AgregadoGenero(BaseModel):
    genero: str
    jogos: int
    jogadores_simultaneos: int | None
    nota_avaliacoes_media: Decimal | None


# ---------------------------------------------------------------------------
# Partidas (Dota 2)
# ---------------------------------------------------------------------------


class JogoDisponivel(BaseModel):
    """Um jogo do star schema e o quanto ja foi coletado dele.

    `equipes` e `agenda` existem porque, com 74 jogos cadastrados e um so com
    partidas, "partidas" sozinho diria que o projeto cobre um jogo. Um jogo com
    600 equipes e 40 confrontos agendados nao esta vazio - esta esperando a
    coleta de partidas, que e outra fonte.
    """

    codigo: str
    nome: str
    partidas: int
    equipes: int = 0
    agenda: int = 0


class ResumoPersonagem(BaseModel):
    """Agregacao por heroi. `winrate` ja vem em pontos percentuais (0-100)."""

    id_personagem: int
    nome: str
    nome_interno: str | None
    partidas: int
    vitorias: int
    winrate: float
    kda_medio: float | None
    kills_media: float | None
    deaths_media: float | None
    assists_media: float | None
    economia_por_minuto_media: float | None
    experiencia_por_minuto_media: float | None


class Partida(BaseModel):
    id_partida: int
    id_externo: str
    data_inicio: datetime | None
    duracao_segundos: int | None
    modo: str | None
    tipo_partida: str | None
    patch: str | None
    liga_nome: str | None
    vencedor: str | None


class JogadorNaPartida(BaseModel):
    slot: int
    equipe: str | None
    vitoria: bool | None
    jogador: str | None
    id_jogador: int | None
    personagem: str | None
    #: `npc_dota_hero_*`, usado para montar a URL do retrato.
    personagem_interno: str | None = None
    kills: int | None
    deaths: int | None
    assists: int | None
    economia: int | None
    economia_por_minuto: int | None
    experiencia_por_minuto: int | None
    last_hits: int | None
    denies: int | None
    nivel: int | None
    dano_causado: int | None
    pontos_objetivo: int | None
    metricas_extras: dict | None


class DetalhePartida(BaseModel):
    partida: Partida
    jogadores: list[JogadorNaPartida]


class FaixaDuracao(BaseModel):
    """Bin do histograma de duracao. `rotulo` ja vem pronto para o eixo."""

    rotulo: str
    minuto_inicial: int
    partidas: int


class FiltrosDisponiveis(BaseModel):
    """Valores distintos das colunas filtraveis, para montar os dropdowns."""

    ligas: list[str]
    modos: list[str]
    patches: list[str]


class ResumoPartidas(BaseModel):
    partidas: int
    jogadores_distintos: int
    personagens_usados: int
    duracao_media_segundos: float | None
    duracao_mediana_segundos: float | None
    winrate_radiant: float | None
    primeira_partida: datetime | None
    ultima_partida: datetime | None
    distribuicao_duracao: list[FaixaDuracao]


class PartidasPorDia(BaseModel):
    data: date
    partidas: int


class ResumoJogador(BaseModel):
    id_jogador: int
    nome: str | None
    partidas: int
    vitorias: int
    winrate: float
    kda_medio: float | None
    economia_por_minuto_media: float | None
    #: Heroi mais escolhido pelo jogador, e em quantas partidas.
    personagem_assinatura: str | None = None
    partidas_assinatura: int | None = None




class EntradaSentimento(BaseModel):
    """Um texto de avaliacao para classificar."""

    texto: str = Field(min_length=1, max_length=8000)


class ResultadoSentimento(BaseModel):
    modelo: str
    probabilidade_positiva: float
    rotulo: str
    caracteres: int
    #: Texto abaixo do minimo usado no treino - a resposta vale menos ali.
    curto: bool


class AvaliacaoClassificada(BaseModel):
    """Uma avaliacao real, com o rotulo do autor e a previsao do modelo."""

    id_externo: str
    texto: str
    #: O polegar do autor. E a verdade.
    recomendado: bool
    criada_em: datetime | None
    minutos_jogados: int | None
    votos_uteis: int | None
    jogo: str
    app_id: int
    probabilidade_positiva: float
    acertou: bool
    modelo: str


class JogoSentimento(BaseModel):
    app_id: int
    jogo: str
    avaliacoes: int
    positivas: int
    percentual_positivo: float


class PontoSentimentoDia(BaseModel):
    dia: date
    avaliacoes: int
    positivas: int
    percentual_positivo: float


class AspectoSentimento(BaseModel):
    """Recorte por palavra-chave, nao por modelo."""

    aspecto: str
    termos: list[str]
    avaliacoes: int
    positivas: int
    percentual_positivo: float


class PanoramaSentimento(BaseModel):
    avaliacoes: int
    positivas: int
    por_jogo: list[JogoSentimento]
    por_dia: list[PontoSentimentoDia]
    aspectos: list[AspectoSentimento]


class ConjuntoSentimento(BaseModel):
    avaliacoes: int
    total_no_banco: int
    descartadas_curtas: int
    minimo_caracteres: int
    jogos: int
    treino: int
    teste: int
    taxa_base: float
    fracao_teste: float
    estratificacao: str


class MetricasSentimento(BaseModel):
    chave: str
    nome: str
    familia: str
    descricao: str
    acuracia: float
    acuracia_balanceada: float
    precisao: float
    revocacao: float
    f1: float
    f1_negativa: float
    roc_auc: float
    log_loss: float
    matriz_confusao: list[list[int]]
    segundos_treino: float
    #: {"positivos": [[termo, peso], ...], "negativos": [...]}. Vazio quando o
    #: modelo nao tem peso por palavra que se leia.
    termos: dict[str, list[list[Any]]]


class ComparacaoSentimento(BaseModel):
    treinado_em: datetime
    idioma: str
    modelo_ativo: str
    conjunto: ConjuntoSentimento
    modelos: list[MetricasSentimento]


class EntradaPergunta(BaseModel):
    """Uma pergunta em linguagem natural sobre os dados coletados."""

    pergunta: str = Field(min_length=3, max_length=500)


class BlocoContexto(BaseModel):
    """Um pedaco do contexto entregue ao modelo, exibido junto da resposta.

    `fonte` separa o que a plataforma mediu ("banco") do que foi lido na loja
    da Steam na hora da pergunta ("steam"). A tela precisa distinguir os dois:
    um numero nosso e um numero externo tem confiabilidade e validade
    diferentes, e chegariam iguais ao leitor sem essa marca.
    """

    chave: str
    titulo: str
    conteudo: str
    fonte: str = "banco"


class JogoRecomendado(BaseModel):
    """Um candidato escolhido por `ml.assistente._recomendacoes`, nao pelo modelo.

    Existe pra tela desenhar um cartao com imagem em vez de so texto - e
    carrega o `app_id` de proposito, que e o que faz o cartao linkar pro
    detalhe do jogo de verdade.
    """

    app_id: int
    nome: str
    generos: list[str]
    nota_avaliacoes: float | None
    jogadores_simultaneos: int | None
    preco: float | None
    moeda: str | None
    gratuito: bool | None


class JogoAoVivo(BaseModel):
    """O jogo citado na pergunta, identificado ao vivo na loja da Steam -
    existe mesmo quando o jogo nunca passou pelo nosso coletor. `ofertas` e
    `menor_historico` vem do IsThereAnyDeal, buscado na hora (nao do coletor
    `itad` em lote), pelo mesmo motivo: o jogo pode nao estar no nosso banco.
    """

    app_id: int
    nome: str
    #: A capa (460x215): pequena, mas nitida e sempre presente.
    imagem_header: str | None
    #: A arte de fundo da loja - grande, mas as vezes ja vem escurecida pela
    #: propria Valve. A tela usa de fundo atras da capa, nao como banner.
    imagem_fundo: str | None = None
    generos: list[str]
    desenvolvedora: str | None
    preco_atual: Decimal | None
    moeda: str | None
    gratuito: bool
    #: Se este jogo ja esta no nosso catalogo (tem serie temporal, avaliacoes
    #: coletadas etc.) ou se so foi consultado agora, so para esta pergunta.
    no_nosso_banco: bool
    ofertas: list[OfertaLoja] = []
    menor_historico: MenorPrecoHistorico | None = None


class RespostaAssistente(BaseModel):
    pergunta: str
    resposta: str
    modelo: str
    #: O que o modelo recebeu. E o que permite conferir cada numero da resposta.
    blocos: list[BlocoContexto]
    #: Preenchido so quando a pergunta pediu recomendacao - a tela desenha um
    #: cartao por item em vez de confiar em texto livre pra saber qual jogo foi
    #: recomendado.
    recomendacoes: list[JogoRecomendado] = []
    #: Preenchido so quando a pergunta citou um jogo que a busca ao vivo achou.
    jogo_ao_vivo: JogoAoVivo | None = None
    tokens_entrada: int | None
    tokens_saida: int | None


# ---------------------------------------------------------------------------
# Previsao de confronto entre equipes (Fase 9)
# ---------------------------------------------------------------------------


class EquipeConfronto(BaseModel):
    id_equipe: int
    nome: str
    tag: str | None
    logo_url: str | None
    partidas: int
    vitorias: int
    winrate: float
    #: Coeficiente de Bradley-Terry. Zero e a media da liga.
    forca: float
    gpm_medio: float | None
    xpm_medio: float | None
    kda_medio: float | None
    duracao_media_segundos: float | None
    #: Saldo medio de placar por confronto, em [-1, 1] (mapas/jogos/pontos
    #: conforme o genero). `None` no Dota e em jogo sem serie 1-contra-1.
    saldo_placar: float | None = None
    #: Posicao e pontos no ranking da Valve (so CS). `None` fora dele.
    posicao_ranking: int | None = None
    pontos_ranking: int | None = None


class FatorConfronto(BaseModel):
    rotulo: str
    valor_a: float | None
    valor_b: float | None
    #: Positivo favorece A.
    diferenca: float | None
    unidade: str
    #: `True` so na forca - os demais sao contexto, nao entram na conta.
    peso_no_modelo: bool


class ValidacaoConfronto(BaseModel):
    avaliadas: int
    suficiente: bool
    motivo: str | None = None
    acuracia: float | None = None
    roc_auc: float | None = None
    log_loss: float | None = None
    brier: float | None = None
    taxa_base: float | None = None
    margem_erro: float | None = None


class PrevisaoConfronto(BaseModel):
    equipe_a: EquipeConfronto
    equipe_b: EquipeConfronto
    probabilidade_a: float
    probabilidade_b: float
    contribuicao_forca: float
    contribuicao_lado: float
    confrontos_diretos: int
    vitorias_diretas_a: int
    fatores: list[FatorConfronto]
    #: Vai junto de proposito: a probabilidade so se lê com ela ao lado.
    validacao: ValidacaoConfronto


class LigaConfronto(BaseModel):
    liga: str
    confrontos: int
    equipes: int
    inicio: datetime | None
    fim: datetime | None


class PrioExternoConfronto(BaseModel):
    """O prior de ranking usado no ajuste (Fase 15). Ausente = Bradley-Terry puro."""

    fonte: str
    #: Peso que a regressao aprendeu para a diferenca de rating. Maior = o
    #: modelo se apoiou mais no ranking externo do que no historico proprio.
    peso: float
    snapshots: int
    data_mais_recente: str
    equipes_no_ranking: int
    equipes_no_ranking_com_confronto: int


class RelatorioConfronto(BaseModel):
    ajustado_em: datetime
    jogo: str
    metodo: str
    regularizacao_C: float
    grade_regularizacao: list[float]
    confrontos: int
    equipes: int
    vantagem_lado_a: float
    probabilidade_lado_a_entre_iguais: float
    primeira_partida: datetime | None
    ultima_partida: datetime | None
    validacao: ValidacaoConfronto
    #: `None` para todo jogo que nao e CS - eles nao tem ranking externo.
    prior_externo: PrioExternoConfronto | None = None
    forcas: dict[str, float]


class ConfrontoAgendado(BaseModel):
    """Um jogo do calendario, com a previsao quando ela e possivel."""

    id_externo: str
    equipe_a_nome: str
    equipe_b_nome: str
    inicio_previsto: datetime
    torneio: str | None
    formato: str | None
    #: `None` quando um dos times nao tem historico coletado.
    probabilidade_a: float | None
    equipe_a: EquipeConfronto | None
    equipe_b: EquipeConfronto | None
    motivo_sem_previsao: str | None


# ---------------------------------------------------------------------------
# Busca no catalogo da Steam e coleta sob demanda (Fase 11)
# ---------------------------------------------------------------------------


class CandidatoJogo(BaseModel):
    """Um resultado da busca no catalogo da Steam."""

    app_id: int
    nome: str
    tipo: str | None
    preco_centavos: int | None
    moeda: str | None
    #: Se ja existe em `dim_jogo_steam` - decide entre mostrar ou coletar.
    coletado: bool
    avaliacoes_coletadas: int
    #: `tiny_image` da busca da loja - ja e a URL real, com hash.
    imagem: str | None = None


class EntradaColeta(BaseModel):
    app_id: int = Field(gt=0)


class ResumoColeta(BaseModel):
    app_id: int
    nome: str
    avaliacoes_coletadas: int
    registros_brutos: int
    segundos: float
