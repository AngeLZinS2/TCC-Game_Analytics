/**
 * As entradas da barra superior, na ordem do desenho do Stitch.
 *
 * O campo `rota` e o que separa uma tela pronta de uma tela so desenhada.
 * "Perfil" ganhou conta de verdade na Fase 31 (Firebase Auth) - clicar leva
 * pra `/perfil`, que pede login/cadastro se ninguem estiver logado
 * (`RotaProtegida`).
 *
 * **E-Sports nao e uma tela, e uma area.** Partidas, Resultados, Previsao,
 * Ranking, Herois e Jogadores eram seis icones na barra, todos dependentes do
 * mesmo jogo escolhido. Viraram sub-abas de uma entrada so; passar o mouse no
 * icone abre o menu de jogos (`menuEsports`), e cada jogo leva para
 * `/esports/<jogo>/partidas`.
 *
 * `chave` (Fase 35) e a chave de traducao em `nav.itens.<chave>` - o rotulo
 * em si nao mora aqui, mora nos arquivos de idioma (`@i18n/locales`), porque
 * este modulo e um `const` estatico e nao pode chamar `useTranslation()`.
 */

export interface ItemNavegacao {
  /** `null` quando a tela ainda nao tem backend. */
  rota: string | null;
  /** Chave de traducao em `nav.itens.<chave>` - o texto mostrado vem de la. */
  chave: string;
  icone: string;
  /** Selo a direita do rotulo, quando ha um - sigla, nao precisa traducao. */
  selo?: string;
  /**
   * O item abre o menu de jogos de E-Sports no hover, em vez de so uma dica.
   * `rota` continua sendo o destino do clique direto (a 1a aba do jogo atual).
   */
  menuEsports?: boolean;
}

export const NAVEGACAO: ItemNavegacao[] = [
  { rota: "/painel", chave: "visaoGeral", icone: "space_dashboard", selo: "LIVE" },

  // Catalogo de Jogos: Steam, PlayStation e Xbox em abas de `/catalogo/:loja`.
  // `rota` e `/catalogo` (nao `/catalogo/steam`) para o `<NavLink>` casar por
  // prefixo em qualquer aba, como o item de E-Sports faz.
  { rota: "/catalogo", chave: "catalogo", icone: "sports_esports" },
  // Promocoes reais da Steam (Fase 35) - preco/desconto do proprio PlayDB,
  // nunca da Steam ao vivo. `local_offer` e o icone padrao do Material p/ oferta.
  { rota: "/ofertas", chave: "ofertas", icone: "local_offer" },
  {
    rota: "/recomendacoes",
    chave: "recomendacoes",
    icone: "sentiment_satisfied",
    selo: "ML",
  },

  // Dominio de esports: partida, resultado, previsao, ranking, heroi e jogador
  // - tudo escopado pelo jogo escolhido no menu que este item abre.
  {
    rota: "/esports",
    chave: "esports",
    icone: "emoji_events",
    menuEsports: true,
  },

  {
    rota: "/assistente",
    chave: "assistente",
    icone: "smart_toy",
    selo: "LLM",
  },
  { rota: "/perfil", chave: "perfil", icone: "account_circle" },
];
