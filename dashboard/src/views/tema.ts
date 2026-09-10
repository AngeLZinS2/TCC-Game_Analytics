/**
 * As cores que o codigo precisa como valor, nao como classe.
 *
 * O Tailwind resolve cor em `class`, e isso cobre quase tudo. O Recharts nao:
 * ele pinta via atributo de apresentacao no SVG (`fill="#5a8cff"`), e atributo
 * nao entende classe nem `var(--token)`. Entao os tokens que aparecem em
 * grafico precisam existir tambem como string literal, e e o que este arquivo e.
 *
 * Os valores sao os mesmos de `tailwind.config.js` - os dois saem do design
 * system "Apex Broadcast Engine" no Stitch. Mudou la, muda nos dois lugares.
 *
 * O design system e escuro e so escuro: `colorMode: DARK`. Nao existe uma
 * segunda paleta desenhada para fundo claro, e inventar uma aqui seria decidir
 * no codigo uma coisa que e do desenho. Por isso o `<html>` fica com `class="dark"`
 * fixo e nao ha seletor de tema.
 */

/** Tokens do design system usados fora de classe Tailwind. */
export const TOKENS = {
  fundo: "#0f1114",
  superficie: "#16191e",
  superficieAlta: "#1e222a",
  contorno: "#6a7280",
  contornoSuave: "#2e333d",
  texto: "#eceef2",
  textoSuave: "#9aa2ae",
  //: Azul — o que é clicável / ativo.
  primaria: "#5a8cff",
  //: Âmbar — reservado ao que o MODELO estima (velocímetro, série de previsão).
  secundaria: "#f3b13b",
  //: Verde — semântico (vitória / ok).
  terciaria: "#40d19e",
  erro: "#ff8a8a",
  //: A "agulha do mostrador" — o mesmo âmbar de `secundaria`, nomeado para
  //: deixar claro no código que é a cor do modelo.
  modelo: "#f3b13b",
} as const;

/**
 * Cores de serie, na ordem em que devem ser usadas.
 *
 * Series diferentes recebem cores diferentes porque a cor identifica *qual*
 * serie e. Num ranking de magnitude a ordem ja esta no comprimento da barra, e
 * ali se usa `PALETA_SERIES[0]` sozinha: colorir cada barra por valor repetiria
 * em cor o que o tamanho ja diz.
 */
export const PALETA_SERIES = [
  TOKENS.primaria,
  TOKENS.secundaria,
  TOKENS.terciaria,
  "#66c0f4",
  "#c7a046",
] as const;

/**
 * Par divergente para winrate.
 *
 * Winrate nao e magnitude, e polaridade: a pergunta e de que lado dos 50% o
 * heroi caiu. Duas cores em torno de um eixo respondem isso; uma escala
 * sequencial nao.
 */
export const PALETA_POLOS = {
  positivo: "#40d19e",
  negativo: "#ff8a8a",
  neutro: TOKENS.contorno,
} as const;

/**
 * Cor de cada jogo — só para orientação (trilho, ponto), nunca preenchimento.
 * Os oito esports do sistema mais a Steam.
 */
export const CORES_JOGO: Record<string, string> = {
  steam: "#66c0f4",
  dota2: "#40d19e",
  counterstrike: "#efa13c",
  valorant: "#ff4655",
  leagueoflegends: "#c7a046",
  lol: "#c7a046",
  callofduty: "#6e7be8",
  overwatch: "#f99e1a",
  rainbowsix: "#2bb0e8",
  rocketleague: "#4c86ff",
};

export function corDoJogo(codigo: string | null | undefined): string {
  return (codigo && CORES_JOGO[codigo]) || TOKENS.primaria;
}

/**
 * Cor estavel de um genero, por hash do nome.
 *
 * O desenho pinta os chips de genero em cores diferentes. Como a lista de
 * generos vem da coleta e nao de uma constante, a cor sai de um hash: "RPG" e
 * sempre da mesma cor, sem um mapa mantido a mao a cada genero novo. Usado
 * pelos catalogos Steam e Xbox (lista e cartao).
 */
export function corDoGenero(genero: string): string {
  let hash = 0;
  for (let i = 0; i < genero.length; i += 1) {
    hash = (hash * 31 + genero.charCodeAt(i)) | 0;
  }
  return PALETA_SERIES[Math.abs(hash) % PALETA_SERIES.length];
}

/** Cor de um valor de winrate em relacao a linha de 50%. */
export function corDoWinrate(winrate: number): string {
  if (winrate > 50) return PALETA_POLOS.positivo;
  if (winrate < 50) return PALETA_POLOS.negativo;
  return PALETA_POLOS.neutro;
}

/** Estilo compartilhado dos eixos e da grade do Recharts. */
export const EIXO = {
  stroke: TOKENS.contornoSuave,
  tick: { fill: TOKENS.textoSuave, fontSize: 11, fontFamily: "IBM Plex Mono" },
} as const;

export const GRADE = {
  stroke: TOKENS.contornoSuave,
  strokeDasharray: "3 3",
  strokeOpacity: 0.5,
} as const;
