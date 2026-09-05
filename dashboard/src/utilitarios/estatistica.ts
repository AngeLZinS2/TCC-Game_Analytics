/**
 * Intervalo de confiança para uma proporção (winrate, pick rate, HS%).
 *
 * Uma taxa é uma estimativa, não um fato: 5 vitórias em 6 partidas dá 83%, mas
 * a próxima partida pode levar isso a 71% ou 86%. O tamanho da amostra é o que
 * separa "83% e nós confiamos" de "83% e pode ser qualquer coisa". Toda tela
 * que mostra uma taxa e a chama de "maior" ou "menor" precisa deste número
 * junto — senão um herói com 17 partidas encabeça o ranking sobre um com 300
 * mil só porque o dado dele é mais barulhento.
 *
 * Usamos o intervalo de **Wilson**, não a aproximação normal (`p ± z·√(p(1-p)/n)`):
 * perto de 0% ou 100%, e com n pequeno — exatamente o caso do ranking de
 * herói —, a aproximação normal estoura para fora de [0, 1] e subestima a
 * incerteza. Wilson se comporta nos dois extremos e é o método padrão para
 * ordenar por taxa quando as amostras são desiguais (Wilson 1927; a mesma
 * conta do "how not to sort by average rating" de Evan Miller).
 */

/** z para 95% de confiança (bicaudal). */
const Z_95 = 1.959963984540054;

export interface IntervaloProporcao {
  /** A estimativa pontual, em fração [0, 1]. */
  taxa: number;
  /** Limite inferior do intervalo de 95%, em fração. */
  minimo: number;
  /** Limite superior do intervalo de 95%, em fração. */
  maximo: number;
  /** Meia-largura do intervalo, em pontos percentuais — o "±" de um KPI. */
  margemPp: number;
}

/**
 * Intervalo de Wilson de 95% para `sucessos` em `total` tentativas.
 *
 * `total` zero devolve o intervalo trivial [0, 1] com taxa 0 — não há o que
 * estimar, e é responsabilidade de quem chama decidir se mostra ou esconde.
 */
export function intervaloWilson(
  sucessos: number,
  total: number,
): IntervaloProporcao {
  if (total <= 0) {
    return { taxa: 0, minimo: 0, maximo: 1, margemPp: 50 };
  }

  const p = Math.min(1, Math.max(0, sucessos / total));
  const z2 = Z_95 * Z_95;
  const denominador = 1 + z2 / total;
  const centro = (p + z2 / (2 * total)) / denominador;
  const desvio =
    (Z_95 * Math.sqrt((p * (1 - p)) / total + z2 / (4 * total * total))) /
    denominador;

  const minimo = Math.max(0, centro - desvio);
  const maximo = Math.min(1, centro + desvio);

  return {
    taxa: p,
    minimo,
    maximo,
    margemPp: ((maximo - minimo) / 2) * 100,
  };
}

/**
 * O quanto a taxa se afasta de `referencia` (padrão 50%) **com** 95% de
 * confiança, em fração e com sinal.
 *
 * - Intervalo inteiramente acima da referência → distância do limite inferior
 *   até ela (positivo).
 * - Intervalo inteiramente abaixo → distância do limite superior (negativo).
 * - Intervalo cruza a referência → `0`: a amostra não permite afirmar de que
 *   lado o herói está.
 *
 * É por este número que o gráfico divergente escolhe quem mostrar: um herói a
 * 78% em 9 partidas tem intervalo [45%, 94%], cruza os 50%, e não entra — o
 * ponto dele parece extremo, mas não sabemos disso.
 */
export function desvioConfiavel(
  sucessos: number,
  total: number,
  referencia = 0.5,
): number {
  const { minimo, maximo } = intervaloWilson(sucessos, total);
  if (minimo > referencia) return minimo - referencia;
  if (maximo < referencia) return maximo - referencia;
  return 0;
}
