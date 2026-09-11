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
  /** Jogos no catálogo da Xbox Store coletados (mercado BR). */
  jogos_xbox: number;
  /** Soma do último snapshot dos jogos monitorados — NÃO é o total da Steam. */
  jogadores_simultaneos_total: number | null;
  /** Usuários conectados à Steam agora (número da plataforma, da Valve). */
  steam_usuarios_online: number | null;
  /** O subconjunto que está dentro de um jogo. */
  steam_usuarios_em_jogo: number | null;
  /** Variação % de `steam_usuarios_online` vs a coleta anterior. */
  steam_usuarios_online_variacao: number | null;
  partidas: number;
  linhas_fato_partida: number;
  jogadores: number;
  personagens: number;
  coletas: ColetaFonte[];
}

export interface MaisJogadoSteam {
  posicao: number;
  app_id: number;
  nome: string | null;
  /** Jogadores dentro do jogo neste instante. */
  jogadores_agora: number;
  pico_24h: number | null;
  /** Movimento vs semana passada: >0 subiu, <0 caiu, 0 igual, `null` novo. */
  variacao_semana: number | null;
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
  /**
   * A capa real da Steam. Vem na lista (e não só na ficha) porque o palpite
   * determinístico de CDN dá 404 nos jogos novos — eles migraram para um
   * caminho com hash, e a linha ficava com a inicial do nome no lugar da capa.
   */
  imagem_header: string | null;
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

/**
 * Um item da galeria da loja: um trailer ou uma captura de tela.
 *
 * `tipo` decide como o carrossel se comporta: `video` toca (HLS, mudo) e passa
 * pro próximo quando acaba; `imagem` fica alguns segundos e troca.
 */
export interface MidiaJogo {
  tipo: "video" | "imagem";
  url: string;
  /** Só no vídeo: o frame de capa, enquanto o player não começa. */
  cartaz: string;
  titulo: string;
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
  /** Nulo quando o jogo não publica recomendado — a tela some com a aba. */
  requisitos_recomendados: string | null;
  /** Trailers e capturas da loja, na ordem do carrossel do topo da ficha. */
  midias: MidiaJogo[];
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

// ---------------------------------------------------------------------------
// Catalogo Xbox (Fase 26) — vitrine de loja, sem CCU nem ML
// ---------------------------------------------------------------------------

export interface JogoXbox {
  product_id: string;
  nome: string;
  tipo: string | null;
  desenvolvedora: string | null;
  publicadora: string | null;
  data_lancamento: string | null;
  generos: string[];
  gratuito: boolean | null;
  preco_no_momento: Decimal | null;
  preco_normal: Decimal | null;
  moeda: string | null;
  desconto_percentual: number | null;
  /** Está no catálogo do Game Pass agora. */
  no_game_pass: boolean | null;
  /** Arte larga (SuperHeroArt), para o topo da ficha. */
  imagem_header: string | null;
  /** Arte quadrada (Poster/BoxArt), para a lista. */
  imagem_capa: string | null;
  url_loja: string | null;
  faixa_etaria: number | null;
  janela_coleta: string | null;
  /** Descrição curta da loja (ShortDescription). */
  descricao: string | null;
  /** Estrela da Microsoft Store, 0–5, desde sempre. */
  nota: number | null;
  numero_avaliacoes: number | null;
  /** Estrela dos últimos 7 dias — o sinal de "como anda a recepção agora". */
  nota_recente: number | null;
  /** Recursos em pt-BR: "4K", "HDR", "Co-op online", "Smart Delivery"... */
  recursos: string[];
  tem_conquistas: boolean | null;
  /** Faixa etária declarada ("14", "M", "18"...). */
  classificacao_etaria: string | null;
  /** Descritores de conteúdo em pt-BR ("Violência", "Linguagem imprópria"...). */
  descritores_conteudo: string[];
}

export interface PontoSerieXbox {
  janela_coleta: string;
  preco_no_momento: Decimal | null;
  preco_normal: Decimal | null;
  desconto_percentual: number | null;
  no_game_pass: boolean | null;
  /** Estrela da loja nessa coleta — satisfação ao longo do tempo. */
  nota: number | null;
}

export interface DetalheJogoXbox {
  jogo: JogoXbox;
  serie: PontoSerieXbox[];
  /**
   * Trailers e capturas da página da loja, no mesmo formato da galeria da
   * Steam (`MidiaJogo`) — o `CarrosselMidia` é o mesmo componente. Trailer
   * (HLS) primeiro, capturas depois.
   */
  midias: MidiaJogo[];
}

export interface FiltrosJogosXbox {
  busca?: string;
  genero?: string;
  ordenar_por?: "game_pass" | "nome" | "preco" | "nota";
  ordem?: "asc" | "desc";
  limite?: number;
}

/** Um resultado da busca na Microsoft Store — o catálogo Xbox só tem quem
 * passou pelo Game Pass ou pela semente fixa; isto acha o resto. */
export interface CandidatoJogoXbox {
  product_id: string;
  nome: string;
  publicadora: string | null;
  preco_texto: string | null;
  coletado: boolean;
  imagem: string | null;
}

export interface ResumoColetaXbox {
  product_id: string;
  nome: string;
  registros_brutos: number;
  segundos: number;
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
  /** Heróis, agentes ou campeões cadastrados. */
  personagens: number;
}

/** Uma coluna de estatística, com o rótulo que o esporte dela usa. */
export interface MetricaEsporte {
  chave: string;
  rotulo: string;
  descricao: string;
  unidade: string;
  casas: number;
  /** `false` em métricas onde menor é melhor (mortes por partida). */
  maior_melhor: boolean;
}

/**
 * Como um esporte nomeia e mede seus personagens.
 *
 * A tela desenhava "KDA / GPM / XPM" fixo, que é o vocabulário do Dota: pedir
 * ouro por minuto de um agente de Valorant é pedir um número que o jogo não
 * produz. `metricas` vazio é a declaração honesta de que não há fonte de
 * estatística por personagem naquele esporte.
 */
export interface PerfilEsporte {
  substantivo: string;
  substantivo_plural: string;
  metricas: MetricaEsporte[];
  fonte: string;
  nota_fonte: string;
  /** `true` quando a API reordena de verdade por `ordenar_por`. */
  ordenavel: boolean;
}

export interface ResumoPersonagem {
  id_personagem: number;
  nome: string;
  nome_interno: string | null;
  partidas: number;
  vitorias: number;
  winrate: number;
  /** Função no time, quando a fonte declara ("Duelista", "Sentinela"). */
  papel: string | null;
  /** Retrato quadrado, na CDN do jogo. `null` cai no quadrado com a inicial. */
  icone: string | null;
  /** As métricas do esporte, pela chave que o perfil declara. */
  metricas: Record<string, number | null>;
}

export interface HabilidadePersonagem {
  slot: string | null;
  nome: string;
  descricao: string | null;
  icone: string | null;
  /** Clipe curto da habilidade (mp4, CDN da Riot). `null` quando não há. */
  video: string | null;
}

/** O desempenho do personagem num mapa/rota específico. */
export interface EstatisticaMapa {
  mapa: string;
  partidas: number;
  vitorias: number;
  winrate: number;
  metricas: Record<string, number | null>;
}

/** Um item da build, com ícone quando a fonte do jogo tem. */
export interface ItemGuia {
  nome: string;
  icone: string | null;
}

/** Um estágio da build: iniciais, núcleo, meio de jogo… */
export interface GrupoGuia {
  titulo: string;
  itens: ItemGuia[];
  /** "74% escolhem" — só quando a fonte dá a taxa. */
  nota: string | null;
}

/** Uma página de runa (LoL) — a árvore e as escolhas dentro dela. */
export interface RunaGuia {
  pagina: string;
  escolhas: string[];
}

/** Uma sequência de habilidades, com o vídeo de demonstração (YouTube, LoL). */
export interface ComboGuia {
  nome: string;
  url: string;
}

/** Como jogar o personagem no meta atual: build, runas, ordem de skill. */
export interface GuiaPersonagem {
  fonte: string;
  rota: string | null;
  atualizado_em: string | null;
  grupos: GrupoGuia[];
  feiticos: string[];
  runa_primaria: RunaGuia | null;
  runa_secundaria: RunaGuia | null;
  /** A sequência de níveis: `["W","Q","E","Q",…]` (LoL). */
  ordem_habilidades: string[];
  /** A prioridade de maximizar: `["Q","W","E"]` (LoL). */
  prioridade_habilidades: string[];
  combos: ComboGuia[];
  /** Por que não há ordem de skill (Dota). */
  nota_habilidades: string | null;
}

/**
 * A ficha completa de um personagem — o equivalente da tela de agente do OP.GG.
 *
 * A parte estática (lore, retrato, habilidades) vem da API do jogo; os números
 * geral e por mapa vêm do OP.GG. O que uma fonte não dá fica nulo.
 */
export interface DetalhePersonagem {
  id_personagem: number;
  nome: string;
  nome_interno: string | null;
  papel: string | null;
  jogo: string;
  descricao: string | null;
  icone: string | null;
  retrato: string | null;
  fundo: string | null;
  habilidades: HabilidadePersonagem[];
  perfil: PerfilEsporte;
  geral: ResumoPersonagem | null;
  /** Do melhor winrate ao pior. Vazio fora do Valorant, por ora. */
  por_mapa: EstatisticaMapa[];
  /** Build e ordem de skill do meta. Nulo onde não há fonte (Valorant). */
  guia: GuiaPersonagem | null;
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
  /** Lado A = Radiant, lado B = Dire. Nulos em qualificatória aberta. */
  equipe_a_nome: string | null;
  equipe_b_nome: string | null;
  equipe_a_logo: string | null;
  equipe_b_logo: string | null;
  equipe_a_tag: string | null;
  equipe_b_tag: string | null;
  /** `true` se o Radiant venceu, `false` se o Dire, `null` sem resultado. */
  vitoria_a: boolean | null;
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
  /** Dota: ouro/min. LoL: ouro por jogo (o feed não dá duração confiável). */
  economia_por_minuto_media: number | null;
  /** Heroi mais escolhido pelo jogador, e em quantas partidas. */
  personagem_assinatura: string | null;
  partidas_assinatura: number | null;
  /** Só LoL (elenco da API oficial): time atual, rota e foto do jogador. */
  equipe_nome: string | null;
  papel: string | null;
  imagem: string | null;
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

/** Sintese por IA (Groq) do que as avaliacoes de um jogo dizem. Gerada em
 * lote pelo agendador, nao em tempo real - `gerado_em`/`avaliacoes_usadas`
 * deixam isso claro na tela. */
export interface ResumoReviews {
  app_id: number;
  texto: string;
  positivos: string[];
  negativos: string[];
  gerado_em: string;
  modelo: string;
  avaliacoes_usadas: number;
}

/** O `ResumoReviews` acima, cruzado da versão Steam do MESMO jogo — a Xbox
 * Store não publica texto de avaliação, só nota agregada. */
export interface ResumoReviewsXbox {
  steam_app_id: number;
  steam_nome: string;
  resumo: ResumoReviews;
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

export interface ChamadaAssistente {
  quando: string;
  sucesso: boolean;
  status_http: number | null;
  rate_limited: boolean;
  erro: string | null;
  duracao_ms: number;
}

/** Telemetria em tempo real das chamadas ao OpenRouter — o painel "Status da
 * API" usa isto pra explicar um 429 do provedor na hora, em vez de parecer
 * bug nosso. `chamadas` vem mais recente primeiro. */
export interface SaudeAssistente {
  configurado: boolean;
  modelo: string;
  total_recente: number;
  sucessos_recente: number;
  taxa_sucesso: number | null;
  rate_limited_recente: boolean;
  ultima_chamada_em: string | null;
  ultima_chamada_sucesso: boolean | null;
  ultima_chamada_erro: string | null;
  chamadas: ChamadaAssistente[];
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
  /** Vem preenchida na descoberta ao vivo; `null` no caminho do catálogo. */
  imagem_header: string | null;
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

export interface PontoSerieAssistente {
  rotulo: string;
  valor: number;
  detalhe: string | null;
}

/**
 * Os numeros de um bloco de contexto, ja estruturados pelo backend.
 *
 * Existe pra tela poder desenhar grafico sem reler o texto da resposta: a serie
 * nasce da mesma consulta que escreveu o bloco. Quando a pergunta nao trouxe
 * nenhum bloco com ranking numerico a lista vem vazia - e ai a tela nao desenha
 * nada, em vez de inventar pontos.
 */
export interface SerieAssistente {
  chave: string;
  titulo: string;
  unidade: string;
  itens: PontoSerieAssistente[];
}

export interface FonteWeb {
  url: string;
  titulo: string;
}

export interface RespostaAssistente {
  pergunta: string;
  resposta: string;
  modelo: string;
  /** O que o modelo recebeu - permite conferir cada numero da resposta. */
  blocos: BlocoContexto[];
  /** As paginas da busca na web, quando a base nao respondeu. */
  fontes_web: FonteWeb[];
  /** Preenchido so quando a pergunta pediu recomendacao de jogo. */
  recomendacoes: JogoRecomendado[];
  /** Preenchido so quando a pergunta citou um jogo que a busca ao vivo achou. */
  jogo_ao_vivo: JogoAoVivo | null;
  /** Os numeros dos blocos usados. Vazia quando nada era comparavel. */
  series: SerieAssistente[];
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
  /** `true` para a força e as features de contexto que o modelo pesou. */
  peso_no_modelo: boolean;
}

export interface ContribuicaoConfronto {
  rotulo: string;
  /** Em log-odds. Positivo empurra para A. A soma, pela sigmoide, é a probabilidade. */
  log_odds: number;
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
  /** A log-odds decomposta em parcelas: força + lado + forma + h2h + saldo. */
  contribuicoes: ContribuicaoConfronto[];
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
  /** Peso (log-odds/unidade) de cada feature de contexto. ~0 = sem sinal. */
  pesos_features: Record<string, number>;
  forcas: Record<string, number>;
}

/**
 * Um confronto já decidido do calendário.
 *
 * Grão diferente do de `Partida`: aqui é "quem venceu a série", não "o que
 * aconteceu dentro dela". Um 3x1 é uma linha, não três partidas — `dim_partida`
 * só existe para Dota 2, onde a OpenDota entrega detalhe por jogador.
 */
export interface FaixaFormato {
  rotulo: string;
  confrontos: number;
}

/**
 * Estatística do calendário — o resumo de quem não tem partida detalhada.
 *
 * Sem duração e sem jogador, e a ausência é o dado: o ticker publica quem
 * jogou, quando e o placar da série, nada do que aconteceu dentro dela.
 */
export interface ResumoConfrontos {
  decididos: number;
  futuros: number;
  equipes: number;
  torneios: number;
  vitorias_lado_a: number;
  winrate_lado_a: number | null;
  primeiro_confronto: string | null;
  ultimo_confronto: string | null;
  por_formato: FaixaFormato[];
  por_dia: PartidasPorDia[];
}

export interface PartidaAgendada {
  id_externo: string;
  equipe_a_nome: string;
  equipe_b_nome: string;
  equipe_a_logo: string | null;
  equipe_b_logo: string | null;
  equipe_a_tag: string | null;
  equipe_b_tag: string | null;
  /** ISO. O horário do vlr.gg não tem fuso confiável — tratar como "por volta de". */
  inicio_previsto: string;
  torneio: string | null;
  formato: string | null;
  /** Canais onde a partida vai passar (PandaScore). Vazio quando não há dado. */
  streams?: StreamCanal[];
}

export interface ConfrontoResultado {
  id_externo: string;
  equipe_a_nome: string;
  equipe_b_nome: string;
  equipe_a_logo: string | null;
  equipe_b_logo: string | null;
  equipe_a_tag: string | null;
  equipe_b_tag: string | null;
  inicio_previsto: string;
  torneio: string | null;
  formato: string | null;
  placar_a: number | null;
  placar_b: number | null;
  /** `null` em empate — existe em fase de grupos de alguns formatos. */
  vitoria_a: boolean | null;
  /** `true` quando há placar por mapa e stats por jogador (Valorant/vlr.gg). */
  tem_detalhe: boolean;
}

export interface JogadorNoMapa {
  nome: string;
  time: string;
  agente: string | null;
  rating: number | null;
  acs: number | null;
  k: number | null;
  d: number | null;
  a: number | null;
  adr: number | null;
  hs: number | null;
  /** LoL: campeão, papel, farm, ouro, nível. */
  campeao: string | null;
  papel: string | null;
  cs: number | null;
  ouro: number | null;
  nivel: number | null;
}

export interface ObjetivosNoMapa {
  torres: number | null;
  baroes: number | null;
  dragoes: number | null;
  ouro: number | null;
}

export interface MapaDoConfronto {
  nome: string | null;
  duracao: string | null;
  placar_a: number | null;
  placar_b: number | null;
  objetivos_a: ObjetivosNoMapa | null;
  objetivos_b: ObjetivosNoMapa | null;
  jogadores: JogadorNoMapa[];
}

/** Um mapa da série, só o resultado (sem stats de jogador). */
export interface ResultadoMapa {
  nome: string | null;
  posicao: number | null;
  /** `encerrado` | `ao_vivo` | `em_breve` | `nao_jogado`. */
  status: string | null;
  placar_a: number | null;
  placar_b: number | null;
  vitoria_a: boolean | null;
}

export type StatusPartida = "em_breve" | "ao_vivo" | "encerrada";

export interface DetalheConfronto {
  id_externo: string;
  equipe_a_nome: string;
  equipe_b_nome: string;
  equipe_a_logo: string | null;
  equipe_b_logo: string | null;
  equipe_a_tag: string | null;
  equipe_b_tag: string | null;
  jogo: string | null;
  jogo_nome: string | null;
  torneio: string | null;
  formato: string | null;
  inicio_previsto: string | null;
  veto: string | null;
  status: StatusPartida;
  placar_a: number | null;
  placar_b: number | null;
  vitoria_a: boolean | null;
  fonte: string;
  streams: StreamCanal[];
  mapas_resultado: ResultadoMapa[];
  mapas: MapaDoConfronto[];
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

// --- Home: acontecendo agora + destaque ---

export interface StreamCanal {
  url: string;
  /** Nome do canal ("PGL") ou a plataforma. */
  nome: string;
  plataforma: string;
  /** Idioma da transmissão ("EN", "PT", "RU"). */
  lingua: string | null;
  /** `true` para a transmissão oficial / principal. */
  principal: boolean;
}

export interface ConfrontoAoVivo {
  id_externo: string;
  jogo: string;
  jogo_nome: string;
  equipe_a_nome: string;
  equipe_b_nome: string;
  equipe_a_logo: string | null;
  equipe_a_tag: string | null;
  equipe_b_logo: string | null;
  equipe_b_tag: string | null;
  torneio: string | null;
  formato: string | null;
  inicio_previsto: string;
  /** `true` quando está mesmo acontecendo (status running, ou começou há pouco). */
  ao_vivo: boolean;
  /** Canais de transmissão (PandaScore). Oficial primeiro. */
  streams: StreamCanal[];
}

export interface DestaqueConfronto extends ConfrontoAoVivo {
  /** Probabilidade de o time A vencer, em [0, 1]. */
  probabilidade_a: number;
}

export interface DestaquesHome {
  ao_vivo: ConfrontoAoVivo[];
  /** `null` quando nenhum confronto próximo tem previsão. */
  destaque: DestaqueConfronto | null;
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
  /** `tiny_image` da busca da loja — já é a URL real, com hash. */
  imagem: string | null;
}

/**
 * Uma linha do catálogo Steam: as duas procedências que a tela junta.
 *
 * `coletado` é um jogo que o pipeline já trouxe (tem telemetria e histórico);
 * `loja` é um jogo que existe na Steam e ainda não entrou. Um union em vez de
 * um `JogoSteam` com tudo nulo — preencher as células de telemetria com zero
 * afirmaria algo falso. Mora aqui (e não em `Steam.tsx`) para o `CartaoJogoSteam`
 * poder importar sem ciclo.
 */
export type LinhaCatalogo =
  | { tipo: "coletado"; jogo: JogoSteam }
  | { tipo: "loja"; candidato: CandidatoJogo };

export interface ResumoColeta {
  app_id: number;
  nome: string;
  avaliacoes_coletadas: number;
  registros_brutos: number;
  segundos: number;
}

// ---------------------------------------------------------------------------
// Ranking oficial por esporte / regiao (/api/esports/ranking-oficial)
// ---------------------------------------------------------------------------
export interface EquipeRankingOficial {
  posicao: number;
  equipe_nome: string;
  id_equipe: number | null;
  tag: string | null;
  logo_url: string | null;
  /** Rating da fonte (ELO ~1000-2000 no vlr.gg). `null` se so publica ordem. */
  pontos: number | null;
  /** V/D de série — só na classificação derivada dos confrontos. */
  vitorias: number | null;
  derrotas: number | null;
}

export interface RegiaoRanking {
  slug: string;
  nome: string;
  equipes: EquipeRankingOficial[];
}

export interface RankingOficial {
  jogo: string;
  /** Nome de exibicao da fonte ("vlr.gg", "Valve Regional Standings"). */
  fonte: string;
  url_fonte: string;
  /** Data do snapshot mais recente (YYYY-MM-DD). */
  data_referencia: string;
  regioes: RegiaoRanking[];
  /** `true` = classificação V-D calculada dos confrontos (sem fonte externa). */
  derivado: boolean;
}
