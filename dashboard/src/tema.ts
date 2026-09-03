/**
 * As cores que o codigo precisa como valor, nao como classe.
 *
 * O Tailwind resolve cor em `class`, e isso cobre quase tudo. O Recharts nao:
 * ele pinta via atributo de apresentacao no SVG (`fill="#00e5ff"`), e atributo
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
  fundo: "#10131a",
  superficie: "#1d1f27",
  superficieAlta: "#272a32",
  contorno: "#849396",
  contornoSuave: "#3b494c",
  texto: "#e1e2ec",
  textoSuave: "#bac9cc",
  primaria: "#00e5ff",
  secundaria: "#c9bfff",
  terciaria: "#16ef7a",
  erro: "#ffb4ab",
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
  "#c89b3c",
] as const;

/**
 * Par divergente para winrate.
 *
 * Winrate nao e magnitude, e polaridade: a pergunta e de que lado dos 50% o
 * heroi caiu. Duas cores em torno de um eixo respondem isso; uma escala
 * sequencial nao.
 */
export const PALETA_POLOS = {
  positivo: "#16ef7a",
  negativo: "#ff8a93",
  neutro: TOKENS.contorno,
} as const;

/** Cores de marca por fonte de dados, como aparecem no desenho do Stitch. */
export const CORES_JOGO: Record<string, string> = {
  steam: "#66c0f4",
  dota2: "#16ef7a",
  lol: "#c89b3c",
  valorant: "#ff4655",
};

export function corDoJogo(codigo: string | null | undefined): string {
  return (codigo && CORES_JOGO[codigo]) || TOKENS.primaria;
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
  tick: { fill: TOKENS.textoSuave, fontSize: 12, fontFamily: "IBM Plex Sans" },
} as const;

export const GRADE = {
  stroke: TOKENS.contornoSuave,
  strokeDasharray: "3 3",
  strokeOpacity: 0.5,
} as const;
