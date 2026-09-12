/**
 * Hooks de leitura (TanStack Query).
 *
 * Uma funcao por endpoint, com a chave de cache espelhando os parametros - e
 * o que permite trocar um filtro sem refazer as consultas vizinhas.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { buscar, chamar, enviar } from "./cliente";
import { cabecalhoAuthAdmin, salvarTokenAdmin, tokenAdmin } from "@models/admin/sessao";
import { cabecalhoAuthUsuario } from "@models/conta/cliente";
import { useUsuario } from "@models/conta/contexto";
import type {
  AgregadoCategoria,
  AgregadoGenero,
  DetalheJogoSteam,
  DetalhePartida,
  FiltrosDisponiveis,
  JogoDisponivel,
  JogoSteam,
  MaisJogadoSteam,
  Partida,
  PartidaAgendada,
  PartidasPorDia,
  PontoSerieTotal,
  ResumoJogador,
  ResumoPartidas,
  AvaliacaoClassificada,
  CandidatoJogo,
  ComparacaoSentimento,
  ConfrontoAgendado,
  ConfrontoResultado,
  DestaquesHome,
  DetalheConfronto,
  DetalheJogoXbox,
  DetalhePersonagem,
  CandidatoJogoXbox,
  FiltrosJogosXbox,
  JogoXbox,
  PerfilEsporte,
  ResumoConfrontos,
  ResumoColetaXbox,
  EquipeConfronto,
  LigaConfronto,
  PanoramaSentimento,
  ResumoReviews,
  ResumoReviewsXbox,
  TokenAdmin,
  VisaoGeralAdmin,
  SaudeSistema,
  SaudeBanco,
  PrevisaoConfronto,
  RankingOficial,
  RelatorioConfronto,
  ResultadoSentimento,
  ResumoColeta,
  RespostaAssistente,
  StatusAssistente,
  SaudeAssistente,
  ResumoPersonagem,
  Saude,
  VisaoGeral,
  PerfilUsuario,
  EntradaHistoricoAssistente,
  JogoFavorito,
  EquipeFavorita,
  ProvedorIA,
  CatalogoModelosIA,
} from "./tipos";

export interface FiltrosJogos {
  busca?: string;
  genero?: string;
  categoria?: string;
  ordenar_por?: string;
  ordem?: "asc" | "desc";
  limite?: number;
}

export function useVisaoGeral() {
  return useQuery({
    queryKey: ["visao-geral"],
    queryFn: () => buscar<VisaoGeral>("/api/visao-geral"),
  });
}

/**
 * Acontecendo agora + o confronto em destaque (com previsão), de todos os
 * jogos. Alimenta o topo da home. O servidor cacheia 3 min; aqui um
 * `refetchInterval` mantém a home viva sem recarregar.
 */
export function useDestaquesHome() {
  return useQuery({
    queryKey: ["home", "destaques"],
    queryFn: () => buscar<DestaquesHome>("/api/home/destaques"),
    staleTime: 120_000,
    refetchInterval: 180_000,
    retry: false,
  });
}

export function useJogosSteam(filtros: FiltrosJogos = {}) {
  return useQuery({
    queryKey: ["steam", "jogos", filtros],
    queryFn: () => buscar<JogoSteam[]>("/api/steam/jogos", { ...filtros }),
    // Segura a lista anterior enquanto o filtro novo carrega, em vez de piscar.
    placeholderData: (anterior) => anterior,
  });
}

export function useGenerosSteam() {
  return useQuery({
    queryKey: ["steam", "generos"],
    queryFn: () => buscar<AgregadoGenero[]>("/api/steam/generos"),
  });
}

/** As categorias da Steam (Single-player, Co-op, Conquistas...) presentes no
 * catálogo, com contagem - popula o dropdown de filtro por categoria. */
export function useCategoriasSteam() {
  return useQuery({
    queryKey: ["steam", "categorias"],
    queryFn: () => buscar<AgregadoCategoria[]>("/api/steam/categorias"),
  });
}

/** Serie do catalogo inteiro somado - o sparkline do KPI de jogadores. */
export function useSerieTotalSteam() {
  return useQuery({
    queryKey: ["steam", "serie-total"],
    queryFn: () => buscar<PontoSerieTotal[]>("/api/steam/serie-total"),
  });
}

/**
 * Top N mais jogados da Steam AGORA. O endpoint já é ao vivo (cache de 90s no
 * servidor); aqui um `staleTime` curto + `refetchInterval` mantêm a home
 * atualizando sozinha sem recarregar a página.
 */
export function useMaisJogadosSteam(limite = 100) {
  return useQuery({
    queryKey: ["steam", "mais-jogados", limite],
    queryFn: () =>
      buscar<MaisJogadoSteam[]>("/api/steam/mais-jogados", { limite }),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

export function useJogoSteam(appId: number) {
  return useQuery({
    queryKey: ["steam", "jogo", appId],
    queryFn: () => buscar<DetalheJogoSteam>(`/api/steam/jogos/${appId}`),
    enabled: Number.isFinite(appId),
  });
}

export function useJogosDisponiveis() {
  return useQuery({
    queryKey: ["partidas", "jogos"],
    queryFn: () => buscar<JogoDisponivel[]>("/api/partidas/jogos"),
  });
}

/** Ligas, modos e patches que existem de fato - as opcoes dos dropdowns. */
export function useFiltrosPartidas(jogo: string) {
  return useQuery({
    queryKey: ["partidas", "filtros", jogo],
    queryFn: () => buscar<FiltrosDisponiveis>("/api/partidas/filtros", { jogo }),
  });
}

export function useResumoPartidas(jogo: string) {
  return useQuery({
    queryKey: ["partidas", "resumo", jogo],
    queryFn: () => buscar<ResumoPartidas>("/api/partidas/resumo", { jogo }),
  });
}

export function usePartidasPorDia(jogo: string) {
  return useQuery({
    queryKey: ["partidas", "por-dia", jogo],
    queryFn: () => buscar<PartidasPorDia[]>("/api/partidas/por-dia", { jogo }),
  });
}

export interface FiltrosPersonagens {
  jogo: string;
  min_partidas?: number;
  ordenar_por?: string;
  limite?: number;
}

export function usePersonagens(filtros: FiltrosPersonagens) {
  return useQuery({
    queryKey: ["partidas", "personagens", filtros],
    queryFn: () => buscar<ResumoPersonagem[]>("/api/partidas/personagens", { ...filtros }),
    placeholderData: (anterior) => anterior,
  });
}

export function useJogadores(jogo: string, minPartidas = 3, limite = 50) {
  return useQuery({
    queryKey: ["partidas", "jogadores", jogo, minPartidas, limite],
    queryFn: () =>
      buscar<ResumoJogador[]>("/api/partidas/jogadores", {
        jogo,
        min_partidas: minPartidas,
        limite,
      }),
    placeholderData: (anterior) => anterior,
  });
}

export interface FiltrosPartidas {
  jogo: string;
  liga?: string;
  desde?: string;
  limite?: number;
  deslocamento?: number;
}

export function usePartidas(filtros: FiltrosPartidas) {
  return useQuery({
    queryKey: ["partidas", "lista", filtros],
    queryFn: () => buscar<Partida[]>("/api/partidas", { ...filtros }),
    placeholderData: (anterior) => anterior,
  });
}

export function usePartida(idPartida: number) {
  return useQuery({
    queryKey: ["partidas", "detalhe", idPartida],
    queryFn: () => buscar<DetalhePartida>(`/api/partidas/${idPartida}`),
    enabled: Number.isFinite(idPartida),
  });
}

/**
 * `/health` com o tempo de ida e volta medido aqui.
 *
 * O rodape da barra lateral mostra esse numero. A API nao devolve latencia -
 * nem teria como: o que interessa e o atraso que *este* navegador vê. Por isso
 * o cronometro fica no cliente, em volta do fetch.
 *
 * Reconsulta sozinho a cada 30s porque e um indicador de status: um valor
 * congelado da primeira carga diria que a API esta no ar muito depois de ela
 * ter caido.
 */
export function useSaude() {
  return useQuery({
    queryKey: ["saude"],
    queryFn: async (): Promise<Saude> => {
      const inicio = performance.now();
      const corpo = await buscar<Omit<Saude, "latenciaMs">>("/health");
      return { ...corpo, latenciaMs: Math.round(performance.now() - inicio) };
    },
    refetchInterval: 30_000,
    staleTime: 0,
    retry: false,
  });
}

// ---------------------------------------------------------------------------
// Machine learning (Fase 6)
// --- Sentimento das avaliacoes (Fase 7) ---

export function useComparacaoSentimento() {
  return useQuery({
    queryKey: ["sentimento", "comparacao"],
    queryFn: () => buscar<ComparacaoSentimento>("/api/ml/sentimento/comparacao"),
    retry: false,
  });
}

/** Contagens sobre o rotulo verdadeiro - nao passa pelo modelo. */
export function usePanoramaSentimento(appId: number | null) {
  return useQuery({
    queryKey: ["sentimento", "panorama", appId],
    queryFn: () =>
      buscar<PanoramaSentimento>(
        "/api/ml/sentimento/panorama",
        appId ? { app_id: appId } : undefined,
      ),
    retry: false,
  });
}

/** Resumo por IA (Groq) das avaliacoes do jogo - cacheado, gerado em lote.
 * 404 quando o jogo ainda nao tem avaliacoes suficientes ou a rodada do
 * agendador ainda nao chegou nele; a tela trata como "ainda sem resumo". */
export function useResumoReviews(appId: number | null) {
  return useQuery({
    queryKey: ["sentimento", "resumo", appId],
    queryFn: () =>
      buscar<ResumoReviews>("/api/ml/sentimento/resumo", { app_id: appId }),
    enabled: appId !== null,
    retry: false,
  });
}

export function useAvaliacoesClassificadas(
  appId: number | null,
  apenasErros: boolean,
  modelo?: string,
) {
  return useQuery({
    queryKey: ["sentimento", "avaliacoes", appId, apenasErros, modelo ?? "ativo"],
    queryFn: () =>
      buscar<AvaliacaoClassificada[]>("/api/ml/sentimento/avaliacoes", {
        app_id: appId ?? undefined,
        apenas_erros: apenasErros,
        modelo,
        // A tela pagina no client (10/página); traz um lote maior de uma vez.
        limite: 120,
      }),
    placeholderData: (anterior) => anterior,
    retry: false,
  });
}

/**
 * Classifica um texto digitado.
 *
 * `enabled` so dispara com texto suficiente: mandar a cada tecla encheria a
 * fila de requisicoes para responder sobre uma frase pela metade.
 */
export function useClassificarSentimento(texto: string, modelo?: string) {
  return useQuery({
    queryKey: ["sentimento", "classificar", texto, modelo ?? "ativo"],
    queryFn: () =>
      enviar<ResultadoSentimento>(
        "/api/ml/sentimento/classificar",
        { texto },
        modelo ? { modelo } : undefined,
      ),
    enabled: texto.trim().length >= 3,
    placeholderData: (anterior) => anterior,
    retry: false,
  });
}

// --- Assistente de dados (Fase 8) ---

/**
 * Confrontos já decididos do calendário, para qualquer jogo cadastrado.
 *
 * Existe porque a tela de Partidas lê `dim_partida`, que só tem linha para
 * Dota 2: para os outros 13 jogos ela ficava vazia embora o banco tivesse 693
 * confrontos com placar. Este hook é o que enche a tela deles.
 */
/**
 * Estatística do calendário, para o jogo sem partida detalhada.
 *
 * A tela de Partidas lê `dim_partida`, que só existe para Dota 2: os outros
 * treze esportes abriam tudo zerado tendo confronto e placar no banco.
 */
/**
 * O vocabulário de estatística do esporte: como ele chama seus personagens e
 * o que ele mede. A tela desenha as colunas a partir daqui.
 */
export function usePerfilEsporte(jogo: string) {
  return useQuery({
    queryKey: ["partidas", "perfil", jogo],
    queryFn: () => buscar<PerfilEsporte>("/api/partidas/perfil", { jogo }),
  });
}

/** A ficha completa de um personagem: quem é, o que faz, como vai por mapa. */
export function useDetalhePersonagem(idPersonagem: number) {
  return useQuery({
    queryKey: ["partidas", "personagem", idPersonagem],
    queryFn: () =>
      buscar<DetalhePersonagem>(`/api/partidas/personagens/${idPersonagem}`),
  });
}

export function useResumoConfrontos(jogo: string) {
  return useQuery({
    queryKey: ["partidas", "resumo-confrontos", jogo],
    queryFn: () =>
      buscar<ResumoConfrontos>("/api/partidas/resumo-confrontos", { jogo }),
  });
}

/**
 * Próximas partidas do jogo (as que ainda vão acontecer). O coletor roda a
 * cada 5 min; aqui `refetchInterval` faz a aba acompanhar sem recarregar.
 */
export function useAgendaPartidas(jogo: string, limite = 60) {
  return useQuery({
    queryKey: ["partidas", "agenda", jogo, limite],
    queryFn: () =>
      buscar<PartidaAgendada[]>("/api/partidas/agenda", { jogo, limite }),
    staleTime: 60_000,
    refetchInterval: 300_000,
  });
}

export function useConfrontos(jogo: string, pagina = 1, limite = 20) {
  return useQuery({
    queryKey: ["partidas", "confrontos", jogo, pagina, limite],
    queryFn: () =>
      buscar<ConfrontoResultado[]>("/api/partidas/confrontos", {
        jogo,
        pagina,
        limite,
      }),
    placeholderData: (anterior) => anterior,
  });
}

export function useConfrontoDetalhe(idExterno: string | null) {
  return useQuery({
    queryKey: ["partidas", "confronto-detalhe", idExterno],
    enabled: idExterno !== null,
    // Enquanto o modal está aberto, revalida de minuto em minuto — se a
    // partida estiver ao vivo o placar/mapa anda.
    staleTime: 30_000,
    refetchInterval: 60_000,
    queryFn: () =>
      buscar<DetalheConfronto>("/api/partidas/confronto-detalhe", {
        id_externo: idExterno as string,
      }),
  });
}

export function useStatusAssistente() {
  return useQuery({
    queryKey: ["assistente", "status"],
    queryFn: () => buscar<StatusAssistente>("/api/assistente/status"),
    retry: false,
  });
}

/** Telemetria em tempo real das chamadas ao OpenRouter (rate limit, erro,
 * taxa de sucesso). Reconsulta sozinho a cada 15s - é o que faz o painel de
 * "Status da API" parecer vivo sem a pessoa precisar recarregar a tela. */
export function useSaudeAssistente() {
  return useQuery({
    queryKey: ["assistente", "saude"],
    queryFn: () => buscar<SaudeAssistente>("/api/assistente/saude"),
    refetchInterval: 15000,
    retry: false,
  });
}

/**
 * Envia uma pergunta ao assistente.
 *
 * Aqui e `useMutation`, nao `useQuery`: a chamada custa tokens e leva segundos,
 * entao ela tem que acontecer quando a pessoa manda, e nao a cada tecla.
 */
export function usePerguntarAssistente() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: async (pergunta: string) =>
      enviar<RespostaAssistente>(
        "/api/assistente/perguntar",
        { pergunta },
        undefined,
        await cabecalhoAuthUsuario(),
      ),
    // A pergunta ja entra no historico do lado do backend (Fase 31) - aqui so
    // invalida o cache pra "Perfil" e a lateral do assistente mostrarem ela.
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["usuario", "historico-assistente"] });
      cliente.invalidateQueries({ queryKey: ["usuario", "perfil"] });
    },
  });
}

// --- Conta de usuario (Fase 31) ---

export function usePerfilUsuario() {
  const { usuario } = useUsuario();
  return useQuery({
    queryKey: ["usuario", "perfil"],
    queryFn: async () =>
      buscar<PerfilUsuario>("/api/usuario/perfil", undefined, await cabecalhoAuthUsuario()),
    enabled: !!usuario,
    retry: false,
  });
}

/** Historico de perguntas ao Assistente, guardado por conta (troca o antigo
 * `localStorage` de `assistente/historico.ts`). */
export function useHistoricoAssistenteServidor() {
  const { usuario } = useUsuario();
  return useQuery({
    queryKey: ["usuario", "historico-assistente"],
    queryFn: async () =>
      buscar<EntradaHistoricoAssistente[]>(
        "/api/usuario/historico-assistente",
        undefined,
        await cabecalhoAuthUsuario(),
      ),
    enabled: !!usuario,
    retry: false,
  });
}

export function useAvaliarPerguntaAssistente() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, util }: { id: number; util: boolean | null }) =>
      chamar(
        `/api/usuario/historico-assistente/${id}`,
        "PATCH",
        { util },
        await cabecalhoAuthUsuario(),
      ),
    onSuccess: () =>
      cliente.invalidateQueries({ queryKey: ["usuario", "historico-assistente"] }),
  });
}

export function useLimparHistoricoAssistente() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      chamar(
        "/api/usuario/historico-assistente",
        "DELETE",
        undefined,
        await cabecalhoAuthUsuario(),
      ),
    onSuccess: () =>
      cliente.invalidateQueries({ queryKey: ["usuario", "historico-assistente"] }),
  });
}

// --- Favoritos: jogos e equipes (Fase 32) ---

export function useFavoritosJogos() {
  const { usuario } = useUsuario();
  return useQuery({
    queryKey: ["usuario", "favoritos", "jogos"],
    queryFn: async () =>
      buscar<JogoFavorito[]>(
        "/api/usuario/favoritos/jogos",
        undefined,
        await cabecalhoAuthUsuario(),
      ),
    enabled: !!usuario,
    retry: false,
  });
}

export function useFavoritarJogo() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: async (entrada: { fonte: "steam" | "xbox"; jogo_id: string }) =>
      enviar<void>("/api/usuario/favoritos/jogos", entrada, undefined, await cabecalhoAuthUsuario()),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["usuario", "favoritos", "jogos"] }),
  });
}

export function useDesfavoritarJogo() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: async (entrada: { fonte: "steam" | "xbox"; jogo_id: string }) =>
      chamar(
        `/api/usuario/favoritos/jogos/${entrada.fonte}/${entrada.jogo_id}`,
        "DELETE",
        undefined,
        await cabecalhoAuthUsuario(),
      ),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["usuario", "favoritos", "jogos"] }),
  });
}

export function useFavoritosEquipes() {
  const { usuario } = useUsuario();
  return useQuery({
    queryKey: ["usuario", "favoritos", "equipes"],
    queryFn: async () =>
      buscar<EquipeFavorita[]>(
        "/api/usuario/favoritos/equipes",
        undefined,
        await cabecalhoAuthUsuario(),
      ),
    enabled: !!usuario,
    retry: false,
  });
}

export function useFavoritarEquipe() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: async (id_equipe: number) =>
      enviar<void>(
        "/api/usuario/favoritos/equipes",
        { id_equipe },
        undefined,
        await cabecalhoAuthUsuario(),
      ),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["usuario", "favoritos", "equipes"] }),
  });
}

export function useDesfavoritarEquipe() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: async (id_equipe: number) =>
      chamar(
        `/api/usuario/favoritos/equipes/${id_equipe}`,
        "DELETE",
        undefined,
        await cabecalhoAuthUsuario(),
      ),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["usuario", "favoritos", "equipes"] }),
  });
}

// --- Chave de IA pessoal (Fase 33) ---

/** Os modelos oferecidos no seletor do Perfil, por provedor.
 *
 * A lista do OpenRouter é buscada ao vivo pelo backend (400+ modelos que
 * mudam toda semana), então vale cache longo aqui: uma vez por sessão basta,
 * e o backend já segura a dele por uma hora. */
export function useModelosIA() {
  return useQuery({
    queryKey: ["assistente", "modelos"],
    queryFn: () => buscar<CatalogoModelosIA>("/api/assistente/modelos"),
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
}

export function useSalvarChaveIA() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: async (entrada: { provedor: ProvedorIA; chave: string; modelo?: string }) =>
      chamar("/api/usuario/chave-ia", "PUT", entrada, await cabecalhoAuthUsuario()),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["usuario", "perfil"] }),
  });
}

export function useRemoverChaveIA() {
  const cliente = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      chamar("/api/usuario/chave-ia", "DELETE", undefined, await cabecalhoAuthUsuario()),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["usuario", "perfil"] }),
  });
}

// --- Previsao de confronto entre equipes (Fase 9) ---
//
// Todos estes hooks recebem `jogo` e o mandam para a API.
//
// Antes nenhum mandava, e o efeito era duplo: trocar o chip do topo nao mudava
// nada na tela, e a API - que sempre teve o parametro com padrao `dota2` -
// respondia sobre Dota 2 independentemente do que estivesse selecionado. O
// `jogo` tambem entra na `queryKey`, senao o cache do TanStack devolveria a
// resposta de um jogo para a pergunta de outro.

export function useRelatorioConfronto(jogo: string) {
  return useQuery({
    queryKey: ["confronto", "relatorio", jogo],
    queryFn: () =>
      buscar<RelatorioConfronto>("/api/ml/confronto/relatorio", { jogo }),
    retry: false,
  });
}

export function useLigasConfronto(jogo: string) {
  return useQuery({
    queryKey: ["confronto", "ligas", jogo],
    queryFn: () => buscar<LigaConfronto[]>("/api/ml/confronto/ligas", { jogo }),
    retry: false,
  });
}

/**
 * O ranking OFICIAL do esporte, por regiao (vlr.gg em Valorant, Valve em CS).
 *
 * 404 quando o jogo nunca teve snapshot coletado - a tela esconde a seção
 * nesse caso, então `retry: false` e o consumidor checa `data`.
 */
export function useRankingOficial(jogo: string) {
  return useQuery({
    queryKey: ["esports", "ranking-oficial", jogo],
    queryFn: () =>
      buscar<RankingOficial>("/api/esports/ranking-oficial", { jogo }),
    retry: false,
  });
}

export function useRankingConfronto(
  jogo: string,
  liga: string | null,
  minPartidas: number,
) {
  return useQuery({
    queryKey: ["confronto", "ranking", jogo, liga, minPartidas],
    queryFn: () =>
      buscar<EquipeConfronto[]>("/api/ml/confronto/ranking", {
        jogo,
        liga: liga ?? undefined,
        min_partidas: minPartidas,
      }),
    placeholderData: (anterior) => anterior,
    retry: false,
  });
}

export function usePrevisaoConfronto(
  jogo: string,
  equipeA: number | null,
  equipeB: number | null,
) {
  return useQuery({
    queryKey: ["confronto", "prever", jogo, equipeA, equipeB],
    queryFn: () =>
      buscar<PrevisaoConfronto>("/api/ml/confronto/prever", {
        jogo,
        equipe_a: equipeA!,
        equipe_b: equipeB!,
      }),
    // Dois times, e times diferentes: sem isso a API responderia 400 a cada
    // render enquanto a pessoa ainda esta escolhendo.
    enabled: equipeA !== null && equipeB !== null && equipeA !== equipeB,
    placeholderData: (anterior) => anterior,
    retry: false,
  });
}

/** Proximos confrontos do calendario, com a previsao de cada um. */
export function useAgendaConfronto(jogo: string, apenasComPrevisao: boolean) {
  return useQuery({
    queryKey: ["confronto", "agenda", jogo, apenasComPrevisao],
    queryFn: () =>
      buscar<ConfrontoAgendado[]>("/api/ml/confronto/agenda", {
        jogo,
        limite: 40,
        apenas_com_previsao: apenasComPrevisao,
      }),
    placeholderData: (anterior) => anterior,
    retry: false,
  });
}

// --- Busca no catalogo da Steam e coleta sob demanda (Fase 11) ---

/**
 * Busca no catalogo COMPLETO da Steam, nao só no que já foi coletado.
 *
 * Debounce fica na tela: aqui o `enabled` só evita disparar com termo curto,
 * que a API rejeitaria de todo jeito.
 */
export function useBuscaCatalogo(termo: string) {
  return useQuery({
    queryKey: ["steam", "catalogo", termo],
    queryFn: () => buscar<CandidatoJogo[]>("/api/steam/catalogo", { termo }),
    enabled: termo.trim().length >= 2,
    placeholderData: (anterior) => anterior,
    retry: false,
  });
}

/**
 * Coleta um jogo da Steam agora.
 *
 * Invalida tudo que depende do catalogo: o jogo novo precisa aparecer na lista,
 * no panorama e nas avaliacoes sem a pessoa recarregar a pagina.
 */
export function useColetarJogo() {
  const cliente = useQueryClient();

  return useMutation({
    mutationFn: (appId: number) =>
      enviar<ResumoColeta>("/api/steam/coletar", { app_id: appId }),
    onSuccess: () => {
      for (const chave of [["steam"], ["sentimento"], ["visao-geral"]]) {
        cliente.invalidateQueries({ queryKey: chave });
      }
    },
  });
}

// --- Catalogo Xbox (Fase 26) — vitrine de loja ---
//
// Sem `refetchInterval`: o coletor roda de 6 em 6 horas e a lista nao muda
// entre uma coleta e outra. `placeholderData` segura a lista atual enquanto
// um filtro novo carrega, como no catalogo da Steam.

export function useJogosXbox(filtros: FiltrosJogosXbox = {}) {
  return useQuery({
    queryKey: ["xbox", "jogos", filtros],
    queryFn: () => buscar<JogoXbox[]>("/api/xbox/jogos", { ...filtros }),
    placeholderData: (anterior) => anterior,
  });
}

export function useGenerosXbox() {
  return useQuery({
    queryKey: ["xbox", "generos"],
    queryFn: () => buscar<AgregadoGenero[]>("/api/xbox/generos"),
  });
}

/** Os recursos do jogo (Co-op online, 4K, Otimizado p/ Series X|S...) -
 * popula o dropdown de categoria da aba Xbox. */
export function useCategoriasXbox() {
  return useQuery({
    queryKey: ["xbox", "categorias"],
    queryFn: () => buscar<AgregadoCategoria[]>("/api/xbox/categorias"),
  });
}

export function useJogoXbox(productId?: string) {
  return useQuery({
    queryKey: ["xbox", "jogo", productId],
    queryFn: () => buscar<DetalheJogoXbox>(`/api/xbox/jogos/${productId}`),
    enabled: !!productId,
  });
}

/** Busca ao vivo na Microsoft Store — o que fecha o buraco de um jogo à
 * venda mas fora do Game Pass e da semente fixa (ex.: um jogo que saiu do
 * Game Pass). Mesmo desenho do `useBuscaCatalogo` da Steam. */
export function useBuscaCatalogoXbox(termo: string) {
  return useQuery({
    queryKey: ["xbox", "catalogo", termo],
    queryFn: () => buscar<CandidatoJogoXbox[]>("/api/xbox/catalogo", { termo }),
    enabled: termo.trim().length >= 2,
    placeholderData: (anterior) => anterior,
    retry: false,
  });
}

/** Coleta um jogo da Microsoft Store agora, achado pelo `/catalogo` acima. */
export function useColetarJogoXbox() {
  const cliente = useQueryClient();

  return useMutation({
    mutationFn: (productId: string) =>
      enviar<ResumoColetaXbox>("/api/xbox/coletar", { product_id: productId }),
    onSuccess: () => {
      for (const chave of [["xbox"], ["visao-geral"]]) {
        cliente.invalidateQueries({ queryKey: chave });
      }
    },
  });
}

/** O resumo por IA da versão Steam do mesmo jogo, se já estiver pronto — a
 * Xbox Store não publica texto de avaliação. 404 (`isError`) quando ainda
 * não há cruzamento pronto; o botão "buscar na Steam" (`useBuscarResumoSteamXbox`
 * abaixo) é quem resolve isso na hora. */
export function useResumoSteamXbox(productId?: string) {
  return useQuery({
    queryKey: ["xbox", "resumo-steam", productId],
    queryFn: () => buscar<ResumoReviewsXbox>(`/api/xbox/jogos/${productId}/resumo-steam`),
    enabled: !!productId,
    retry: false,
  });
}

/** Busca ao vivo na Steam pelo equivalente deste jogo e gera o resumo por IA
 * na hora (busca + coleta + resumo, encadeados) - o caminho pesado, alguns
 * segundos, só quando o `useResumoSteamXbox` acima não achou nada pronto. */
export function useBuscarResumoSteamXbox() {
  const cliente = useQueryClient();

  return useMutation({
    mutationFn: (productId: string) =>
      enviar<ResumoReviewsXbox>(`/api/xbox/jogos/${productId}/resumo-steam`, {}),
    onSuccess: (dados, productId) => {
      cliente.setQueryData(["xbox", "resumo-steam", productId], dados);
    },
  });
}

// --- Painel admin (Fase 30) ---
//
// Sem sistema de contas: uma senha só, token guardado no localStorage
// (`@models/admin/sessao`). Todo hook daqui manda o header `Authorization` e
// só habilita a consulta quando já existe um token salvo — sem isso a tela
// de login nunca chamaria `/api/admin/*` à toa.

export function useLoginAdmin() {
  return useMutation({
    mutationFn: (senha: string) => enviar<TokenAdmin>("/api/admin/login", { senha }),
    onSuccess: (dados) => salvarTokenAdmin(dados.token),
  });
}

export function useVisaoGeralAdmin() {
  return useQuery({
    queryKey: ["admin", "visao-geral"],
    queryFn: () =>
      buscar<VisaoGeralAdmin>("/api/admin/visao-geral", undefined, cabecalhoAuthAdmin()),
    enabled: !!tokenAdmin(),
    retry: false,
  });
}

/** CPU/RAM/disco — reconsulta a cada 10s pra parecer um painel de monitoramento
 * de verdade, não uma foto parada. */
export function useSistemaAdmin() {
  return useQuery({
    queryKey: ["admin", "sistema"],
    queryFn: () => buscar<SaudeSistema>("/api/admin/sistema", undefined, cabecalhoAuthAdmin()),
    enabled: !!tokenAdmin(),
    refetchInterval: 10000,
    retry: false,
  });
}

export function useBancoAdmin() {
  return useQuery({
    queryKey: ["admin", "banco"],
    queryFn: () => buscar<SaudeBanco>("/api/admin/banco", undefined, cabecalhoAuthAdmin()),
    enabled: !!tokenAdmin(),
    retry: false,
  });
}
