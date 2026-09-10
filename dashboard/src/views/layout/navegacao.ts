/**
 * As entradas da barra superior, na ordem do desenho do Stitch.
 *
 * O campo `rota` e o que separa uma tela pronta de uma tela so desenhada.
 * "Perfil" existe no Stitch mas depende de autenticacao, que o projeto nao
 * tem - aparece na navegacao, porque faz parte do desenho do produto, mas nao
 * leva a lugar nenhum e diz isso na propria linha.
 *
 * **E-Sports nao e uma tela, e uma area.** Partidas, Resultados, Previsao,
 * Ranking, Herois e Jogadores eram seis icones na barra, todos dependentes do
 * mesmo jogo escolhido. Viraram sub-abas de uma entrada so; passar o mouse no
 * icone abre o menu de jogos (`menuEsports`), e cada jogo leva para
 * `/esports/<jogo>/partidas`.
 */

export interface ItemNavegacao {
  /** `null` quando a tela ainda nao tem backend. */
  rota: string | null;
  rotulo: string;
  icone: string;
  /** Selo a direita do rotulo, quando ha um. */
  selo?: string;
  /**
   * O item abre o menu de jogos de E-Sports no hover, em vez de so uma dica.
   * `rota` continua sendo o destino do clique direto (a 1a aba do jogo atual).
   */
  menuEsports?: boolean;
}

export const NAVEGACAO: ItemNavegacao[] = [
  { rota: "/", rotulo: "Visão Geral", icone: "space_dashboard", selo: "LIVE" },

  // Catalogo de Jogos: Steam, PlayStation e Xbox em abas de `/catalogo/:loja`.
  // `rota` e `/catalogo` (nao `/catalogo/steam`) para o `<NavLink>` casar por
  // prefixo em qualquer aba, como o item de E-Sports faz.
  { rota: "/catalogo", rotulo: "Catálogo de Jogos", icone: "sports_esports" },
  {
    rota: "/recomendacoes",
    rotulo: "Recomendações por Reviews",
    icone: "sentiment_satisfied",
    selo: "ML",
  },

  // Dominio de esports: partida, resultado, previsao, ranking, heroi e jogador
  // - tudo escopado pelo jogo escolhido no menu que este item abre.
  {
    rota: "/esports",
    rotulo: "E-Sports",
    icone: "emoji_events",
    menuEsports: true,
  },

  {
    rota: "/assistente",
    rotulo: "Assistente de IA",
    icone: "smart_toy",
    selo: "LLM",
  },
  { rota: null, rotulo: "Perfil", icone: "account_circle" },
];
