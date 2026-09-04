/**
 * Espelho TypeScript de `api/schemas.py`.
 *
 * Os nomes seguem os do backend (portugues) de proposito: renomear aqui
 * criaria um dicionario mental a mais entre o banco, a API e a tela.
 *
 * Campos Numeric do Postgres chegam como string no JSON (o Pydantic serializa
 * Decimal assim, para nao perder precisao); por isso `number | string` nos
 * campos monetarios e de nota, sempre passados por `paraNumero()`.
 */

export type Decimal = number | string;

export interface ColetaFonte {
  fonte: string;
  payloads: number;
  ultima_coleta: string | null;
}

export interface VisaoGeral {
  jogos_steam: number;
  snapshots_steam: number;
  jogadores_simultaneos_total: number | null;
  partidas: number;
  linhas_fato_partida: number;
  jogadores: number;
  personagens: number;
  coletas: ColetaFonte[];
}

export interface JogoSteam {
  app_id: number;
  nome: string;
  desenvolvedora: string | null;
  publicadora: string | null;
  data_lancamento: string | null;
  generos: string[];
  gratuito: boolean | null;
  nota_metacritic: number | null;
  janela_coleta: string | null;
  jogadores_simultaneos: number | null;
  nota_avaliacoes: Decimal | null;
  numero_avaliacoes: number | null;
  classificacao_steam: string | null;
  preco_no_momento: Decimal | null;
  moeda: string | null;
  desconto_percentual: number | null;
  /** Maior valor ja coletado para este jogo. */
  pico_jogadores: number | null;
  /** Variacao sobre a coleta anterior. Nulo enquanto so houver uma coleta. */
  variacao_jogadores: number | null;
}

export interface PontoSerie {
  janela_coleta: string;
  jogadores_simultaneos: number | null;
  nota_avaliacoes: Decimal | null;
  numero_avaliacoes: number | null;
  preco_no_momento: Decimal | null;
  desconto_percentual: number | null;
}

export interface PontoSerieTotal {
  janela_coleta: string;
  jogadores_simultaneos: number | null;
  jogos: number;
}

export interface ConquistaDestaque {
  nome: string;
  icone: string;
}

/** Metadados quase estáticos do jogo — a "ficha" estilo SteamDB. */
export interface FichaJogoSteam {
  tipo: string | null;
  recursos: string[];
  plataformas: string[];
  idiomas: string[];
  idiomas_com_audio: string[];
  faixa_etaria: number | null;
  descritores_conteudo: string[];
  classificacoes: Record<string, string>;
  suporte_controle: string | null;
  conquistas_total: number | null;
  conquistas_destaque: ConquistaDestaque[];
  analises_totais: number | null;
  dlc_ids: number[];
  site_oficial: string | null;
  imagem_header: string | null;
  em_breve: boolean | null;
  requisitos_minimos: string | null;
  donos_estimados: string | null;
  tempo_jogo_medio_min: number | null;
  tempo_jogo_mediano_min: number | null;
  /** [tag, votos], já ordenado por votos desc. */
  tags_comunidade: [string, number][];
  coletado_ficha_em: string | null;

  /** HowLongToBeat — casado por nome (Steam e HLTB não compartilham id). */
  hltb_id: string | null;
  /** Nome como aparece no HLTB — confere se o casamento achou o jogo certo. */
  hltb_nome: string | null;
  hltb_horas_historia: Decimal | null;
  hltb_horas_extras: Decimal | null;
  hltb_horas_completista: Decimal | null;
  coletado_tempo_em: string | null;
}

export interface NoticiaSteam {
  gid: string;
  titulo: string;
  url: string | null;
  autor: string | null;
  feed: string | null;
  publicado_em: string | null;
  resumo: string | null;
}

export interface OfertaLoja {
  loja: string;
  preco: Decimal;
  preco_normal: Decimal | null;
  desconto: number | null;
  moeda: string | null;
  url: string | null;
  drm: string | null;
  /** `true` na loja mais barata. */
  melhor: boolean;
}

export interface MenorPrecoHistorico {
  preco: Decimal;
  loja: string | null;
  moeda: string | null;
  data: string | null;
}

export interface DetalheJogoSteam {
  jogo: JogoSteam;
  ficha: FichaJogoSteam;
  noticias: NoticiaSteam[];
  /** Ofertas em outras lojas, da mais barata para a mais cara. */
  ofertas: OfertaLoja[];
  menor_preco_historico: MenorPrecoHistorico | null;
  serie: PontoSerie[];
}

export interface AgregadoGenero {
  genero: string;
  jogos: number;
  jogadores_simultaneos: number | null;
  nota_avaliacoes_media: Decimal | null;
}

export interface JogoDisponivel {
  codigo: string;
  nome: string;
  partidas: number;
  /**
   * Equipes e confrontos agendados do jogo.
   *
   * Existem porque, com 73 jogos cadastrados, "partidas" sozinho diria que o
   * projeto cobre um. Um jogo com 1.409 equipes e 54 confrontos na agenda nao
   * esta vazio - esta esperando a coleta de partidas, que vem de outra fonte.
   */
  equipes: number;
  agenda: number;
}

export interface ResumoPersonagem {
  id_personagem: number;
  nome: string;
  nome_interno: string | null;
  partidas: number;
  vitorias: number;
  winrate: number;
  kda_medio: number | null;
  kills_media: number | null;
  deaths_media: number | null;
  assists_media: number | null;
  economia_por_minuto_media: number | null;
  experiencia_por_minuto_media: number | null;
}

export interface Partida {
  id_partida: number;
  id_externo: string;
  data_inicio: string | null;
  duracao_segundos: number | null;
  modo: string | null;
  tipo_partida: string | null;
  patch: string | null;
  liga_nome: string | null;
  vencedor: string | null;
}

export interface JogadorNaPartida {
  slot: number;
  equipe: string | null;
  vitoria: boolean | null;
  jogador: string | null;
  id_jogador: number | null;
  personagem: string | null;
  /** `npc_dota_hero_*`, usado para montar a URL do retrato. */
  personagem_interno: string | null;
  kills: number | null;
  deaths: number | null;
  assists: number | null;
  economia: number | null;
  economia_por_minuto: number | null;
  experiencia_por_minuto: number | null;
  last_hits: number | null;
  denies: number | null;
  nivel: number | null;
  dano_causado: number | null;
  pontos_objetivo: number | null;
  metricas_extras: Record<string, number | string | null> | null;
}

export interface DetalhePartida {
  partida: Partida;
  jogadores: JogadorNaPartida[];
}

export interface FaixaDuracao {
  rotulo: string;
  minuto_inicial: number;
  partidas: number;
}

export interface FiltrosDisponiveis {
  ligas: string[];
  modos: string[];
  patches: string[];
}

export interface ResumoPartidas {
  partidas: number;
  jogadores_distintos: number;
  personagens_usados: number;
  duracao_media_segundos: number | null;
  duracao_mediana_segundos: number | null;
  winrate_radiant: number | null;
  primeira_partida: string | null;
  ultima_partida: string | null;
  distribuicao_duracao: FaixaDuracao[];
}

export interface PartidasPorDia {
  data: string;
  partidas: number;
}

export interface ResumoJogador {
  id_jogador: number;
  nome: string | null;
  partidas: number;
  vitorias: number;
  winrate: number;
  kda_medio: number | null;
  economia_por_minuto_media: number | null;
  /** Heroi mais escolhido pelo jogador, e em quantas partidas. */
  personagem_assinatura: string | null;
  partidas_assinatura: number | null;
}

export interface Saude {
  status: "ok" | "degradado";
  banco: boolean;
  erro: string | null;
  /** Nao vem da API: e o tempo que a chamada levou, medido no cliente. */
  latenciaMs: number;
}

// --- Sentimento das avaliacoes (Fase 7) ---

export interface EntradaSentimento {
  texto: string;
}

export interface ResultadoSentimento {
  modelo: string;
  probabilidade_positiva: number;
  rotulo: string;
  caracteres: number;
  /** Texto abaixo do minimo usado no treino - a resposta vale menos ali. */
  curto: boolean;
}

export interface AvaliacaoClassificada {
  id_externo: string;
  texto: string;
  /** O polegar do autor. E a verdade. */
  recomendado: boolean;
  criada_em: string | null;
  minutos_jogados: number | null;
  votos_uteis: number | null;
  jogo: string;
  app_id: number;
  probabilidade_positiva: number;
  acertou: boolean;
  modelo: string;
}

export interface JogoSentimento {
  app_id: number;
  jogo: string;
  avaliacoes: number;
  positivas: number;
  percentual_positivo: number;
}

export interface PontoSentimentoDia {
  dia: string;
  avaliacoes: number;
  positivas: number;
  percentual_positivo: number;
}

export interface AspectoSentimento {
  aspecto: string;
  termos: string[];
  avaliacoes: number;
  positivas: number;
  percentual_positivo: number;
}

export interface PanoramaSentimento {
  avaliacoes: number;
  positivas: number;
  por_jogo: JogoSentimento[];
  por_dia: PontoSentimentoDia[];
  aspectos: AspectoSentimento[];
}

export interface ConjuntoSentimento {
  avaliacoes: number;
  total_no_banco: number;
  descartadas_curtas: number;
  minimo_caracteres: number;
  jogos: number;
  treino: number;
  teste: number;
  taxa_base: number;
  fracao_teste: number;
  estratificacao: string;
}

export interface MetricasSentimento {
  chave: string;
  nome: string;
  familia: string;
  descricao: string;
  acuracia: number;
  acuracia_balanceada: number;
  precisao: number;
  revocacao: number;
  f1: number;
  f1_negativa: number;
  roc_auc: number;
  log_loss: number;
  matriz_confusao: number[][];
  segundos_treino: number;
  /** {positivos, negativos}: [termo, peso]. Vazio quando o modelo nao expõe. */
  termos: Record<string, [string, number][]>;
}

export interface ComparacaoSentimento {
  treinado_em: string;
  idioma: string;
  modelo_ativo: string;
  conjunto: ConjuntoSentimento;
  modelos: MetricasSentimento[];
}

// --- Assistente de dados (Fase 8) ---

export interface StatusAssistente {
  configurado: boolean;
  modelo: string;
  provedor: string;
}

export interface BlocoContexto {
  chave: string;
  titulo: string;
  conteudo: string;
  /**
   * De onde o bloco veio: `banco` e medicao nossa, `steam` e a loja consultada
   * no momento da pergunta. A distincao importa ao ler a resposta - um numero
   * nosso e reproduzivel a partir do banco, um numero da loja nao.
   */
  fonte: string;
}

/**
 * Um candidato escolhido pelo Python (`ml.assistente._recomendacoes`), nao
 * pelo modelo - por isso vem com `app_id`: e o que deixa a tela desenhar um
 * cartao de verdade, com imagem e link pro jogo, em vez de tentar adivinhar
 * de qual jogo o texto da resposta estava falando.
 */
export interface JogoRecomendado {
  app_id: number;
  nome: string;
  generos: string[];
  nota_avaliacoes: number | null;
  jogadores_simultaneos: number | null;
  preco: number | null;
  moeda: string | null;
  gratuito: boolean | null;
}

/**
 * O jogo citado na pergunta, identificado ao vivo na loja da Steam — existe
 * mesmo quando o jogo nunca passou pelo nosso coletor. `ofertas` e
 * `menor_historico` vêm do IsThereAnyDeal, buscados na hora.
 */
export interface JogoAoVivo {
  app_id: number;
  nome: string;
  /** A capa (460x215): pequena, mas nítida e sempre presente. */
  imagem_header: string | null;
  /**
   * A arte de fundo da loja — grande, mas às vezes já vem escurecida/borrada
   * pela própria Valve. Serve de fundo atrás da capa, não como banner.
   */
  imagem_fundo: string | null;
  generos: string[];
  desenvolvedora: string | null;
  preco_atual: Decimal | null;
  moeda: string | null;
  gratuito: boolean;
  /** Se este jogo já está no nosso catálogo, ou só foi consultado agora. */
  no_nosso_banco: boolean;
  ofertas: OfertaLoja[];
  menor_historico: MenorPrecoHistorico | null;
}

export interface RespostaAssistente {
  pergunta: string;
  resposta: string;
  modelo: string;
  /** O que o modelo recebeu - permite conferir cada numero da resposta. */
  blocos: BlocoContexto[];
  /** Preenchido so quando a pergunta pediu recomendacao de jogo. */
  recomendacoes: JogoRecomendado[];
  /** Preenchido so quando a pergunta citou um jogo que a busca ao vivo achou. */
  jogo_ao_vivo: JogoAoVivo | null;
  tokens_entrada: number | null;
  tokens_saida: number | null;
}

// --- Previsao de confronto entre equipes (Fase 9) ---

export interface EquipeConfronto {
  id_equipe: number;
  nome: string;
  tag: string | null;
  logo_url: string | null;
  partidas: number;
  vitorias: number;
  winrate: number;
  /** Coeficiente de Bradley-Terry. Zero e a media da liga. */
  forca: number;
  gpm_medio: number | null;
  xpm_medio: number | null;
  kda_medio: number | null;
  duracao_media_segundos: number | null;
  /** Saldo médio de placar por confronto, em [-1, 1] (mapas/jogos/pontos). */
  saldo_placar: number | null;
  /** Posicao e pontos no ranking da Valve (so CS). `null` fora dele. */
  posicao_ranking: number | null;
  pontos_ranking: number | null;
}

export interface FatorConfronto {
  rotulo: string;
  valor_a: number | null;
  valor_b: number | null;
  /** Positivo favorece A. */
  diferenca: number | null;
  unidade: string;
  /** `true` so na forca - os demais sao contexto, nao entram na conta. */
  peso_no_modelo: boolean;
}

export interface ValidacaoConfronto {
  avaliadas: number;
  suficiente: boolean;
  motivo: string | null;
  acuracia: number | null;
  roc_auc: number | null;
  log_loss: number | null;
  brier: number | null;
  taxa_base: number | null;
  margem_erro: number | null;
}

export interface PrevisaoConfronto {
  equipe_a: EquipeConfronto;
  equipe_b: EquipeConfronto;
  probabilidade_a: number;
  probabilidade_b: number;
  contribuicao_forca: number;
  contribuicao_lado: number;
  confrontos_diretos: number;
  vitorias_diretas_a: number;
  fatores: FatorConfronto[];
  validacao: ValidacaoConfronto;
}

export interface LigaConfronto {
  liga: string;
  confrontos: number;
  equipes: number;
  inicio: string | null;
  fim: string | null;
}

export interface PrioExternoConfronto {
  fonte: string;
  /** Peso que a regressao deu para a diferenca de rating do ranking externo. */
  peso: number;
  snapshots: number;
  data_mais_recente: string;
  equipes_no_ranking: number;
  equipes_no_ranking_com_confronto: number;
}

export interface RelatorioConfronto {
  ajustado_em: string;
  jogo: string;
  metodo: string;
  regularizacao_C: number;
  grade_regularizacao: number[];
  confrontos: number;
  equipes: number;
  vantagem_lado_a: number;
  probabilidade_lado_a_entre_iguais: number;
  primeira_partida: string | null;
  ultima_partida: string | null;
  validacao: ValidacaoConfronto;
  /** `null` para todo jogo que nao e CS. */
  prior_externo: PrioExternoConfronto | null;
  forcas: Record<string, number>;
}

export interface ConfrontoAgendado {
  id_externo: string;
  equipe_a_nome: string;
  equipe_b_nome: string;
  inicio_previsto: string;
  torneio: string | null;
  formato: string | null;
  /** `null` quando um dos times nao tem historico coletado. */
  probabilidade_a: number | null;
  equipe_a: EquipeConfronto | null;
  equipe_b: EquipeConfronto | null;
  motivo_sem_previsao: string | null;
}

// --- Busca no catalogo da Steam e coleta sob demanda (Fase 11) ---

export interface CandidatoJogo {
  app_id: number;
  nome: string;
  tipo: string | null;
  preco_centavos: number | null;
  moeda: string | null;
  /** Se ja existe no banco - decide entre mostrar ou oferecer a coleta. */
  coletado: boolean;
  avaliacoes_coletadas: number;
}

export interface ResumoColeta {
  app_id: number;
  nome: string;
  avaliacoes_coletadas: number;
  registros_brutos: number;
  segundos: number;
}
