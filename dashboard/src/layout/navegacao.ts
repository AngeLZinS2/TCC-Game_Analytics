/**
 * As entradas da barra lateral, na ordem do desenho do Stitch.
 *
 * O campo `rota` e o que separa uma tela pronta de uma tela so desenhada.
 * As seis ultimas entradas existem no Stitch mas dependem de modelos que ainda
 * nao existem no backend (`ml/` esta vazio) - elas aparecem na navegacao,
 * porque fazem parte do desenho do produto, mas nao levam a lugar nenhum e
 * dizem isso na propria linha. Uma tela com numero inventado seria pior: ela
 * parece pronta.
 */

export interface ItemNavegacao {
  /** `null` quando a tela ainda nao tem backend. */
  rota: string | null;
  rotulo: string;
  icone: string;
  /** Selo a direita do rotulo, quando ha um. */
  selo?: string;
}

export const NAVEGACAO: ItemNavegacao[] = [
  { rota: "/", rotulo: "Visão Geral", icone: "space_dashboard", selo: "LIVE" },
  { rota: "/steam", rotulo: "Jogos da Steam", icone: "sports_esports" },
  { rota: "/partidas", rotulo: "Partidas", icone: "scoreboard" },
  { rota: "/herois", rotulo: "Heróis", icone: "shield_person" },
  { rota: "/jogadores", rotulo: "Jogadores", icone: "group" },

  {
    rota: "/previsao",
    rotulo: "Previsão de Confronto",
    icone: "swords",
    selo: "ML",
  },
  {
    rota: "/recomendacoes",
    rotulo: "Recomendações por Reviews",
    icone: "sentiment_satisfied",
    selo: "ML",
  },
  {
    rota: "/assistente",
    rotulo: "Assistente de IA",
    icone: "smart_toy",
    selo: "LLM",
  },
  { rota: null, rotulo: "Perfil", icone: "account_circle" },
];
