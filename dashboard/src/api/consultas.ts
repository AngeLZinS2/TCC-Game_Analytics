/**
 * Hooks de leitura (TanStack Query).
 *
 * Uma funcao por endpoint, com a chave de cache espelhando os parametros - e
 * o que permite trocar um filtro sem refazer as consultas vizinhas.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { buscar, enviar } from "./cliente";
import type {
  AgregadoGenero,
  DetalheJogoSteam,
  DetalhePartida,
  FiltrosDisponiveis,
  JogoDisponivel,
  JogoSteam,
  Partida,
  PartidasPorDia,
  PontoSerieTotal,
  ResumoJogador,
  ResumoPartidas,
  AvaliacaoClassificada,
  CandidatoJogo,
  ComparacaoSentimento,
  ConfrontoAgendado,
  ConfrontoResultado,
  PerfilEsporte,
  ResumoConfrontos,
  EquipeConfronto,
  LigaConfronto,
  PanoramaSentimento,
  PrevisaoConfronto,
  RelatorioConfronto,
  ResultadoSentimento,
  ResumoColeta,
  RespostaAssistente,
  StatusAssistente,
  ResumoPersonagem,
  Saude,
  VisaoGeral,
} from "./tipos";

export interface FiltrosJogos {
  busca?: string;
  genero?: string;
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

/** Serie do catalogo inteiro somado - o sparkline do KPI de jogadores. */
export function useSerieTotalSteam() {
  return useQuery({
    queryKey: ["steam", "serie-total"],
    queryFn: () => buscar<PontoSerieTotal[]>("/api/steam/serie-total"),
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
        limite: 20,
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

export function useResumoConfrontos(jogo: string) {
  return useQuery({
    queryKey: ["partidas", "resumo-confrontos", jogo],
    queryFn: () =>
      buscar<ResumoConfrontos>("/api/partidas/resumo-confrontos", { jogo }),
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

export function useStatusAssistente() {
  return useQuery({
    queryKey: ["assistente", "status"],
    queryFn: () => buscar<StatusAssistente>("/api/assistente/status"),
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
  return useMutation({
    mutationFn: (pergunta: string) =>
      enviar<RespostaAssistente>("/api/assistente/perguntar", { pergunta }),
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
