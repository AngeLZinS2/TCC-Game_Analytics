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


class DetalheJogoSteam(BaseModel):
    jogo: JogoSteam
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


class RespostaAssistente(BaseModel):
    pergunta: str
    resposta: str
    modelo: str
    #: O que o modelo recebeu. E o que permite conferir cada numero da resposta.
    blocos: list[BlocoContexto]
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


class EntradaColeta(BaseModel):
    app_id: int = Field(gt=0)


class ResumoColeta(BaseModel):
    app_id: int
    nome: str
    avaliacoes_coletadas: int
    registros_brutos: int
    segundos: float
