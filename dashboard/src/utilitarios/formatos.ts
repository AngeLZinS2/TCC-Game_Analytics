/** Formatadores de exibicao. Todos aceitam nulo e devolvem um travessao. */

const VAZIO = "—"; // travessao: "nao coletado", diferente de zero

const numero = new Intl.NumberFormat("pt-BR");
const numeroCurto = new Intl.NumberFormat("pt-BR", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const dataHora = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
});
const dataCurta = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" });

/**
 * Converte o texto ISO da API em Date.
 *
 * Uma data pura ("2026-08-29") e interpretada como UTC pelo construtor padrao,
 * o que a joga para o dia anterior em qualquer fuso a oeste de Greenwich - o
 * grafico de partidas por dia comecava um dia antes do que o banco diz. Datas
 * puras, entao, sao montadas no fuso local; timestamps completos passam direto.
 */
function paraData(iso: string): Date {
  const soData = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!soData) return new Date(iso);
  return new Date(Number(soData[1]), Number(soData[2]) - 1, Number(soData[3]));
}

/** Numeric do Postgres chega como string no JSON; normaliza para number. */
export function paraNumero(valor: number | string | null | undefined): number | null {
  if (valor === null || valor === undefined || valor === "") return null;
  const n = typeof valor === "number" ? valor : Number(valor);
  return Number.isFinite(n) ? n : null;
}

export function fmtNumero(valor: number | string | null | undefined): string {
  const n = paraNumero(valor);
  return n === null ? VAZIO : numero.format(n);
}

/** Para eixos e KPIs: 536.314 vira "536,3 mil". */
export function fmtCurto(valor: number | string | null | undefined): string {
  const n = paraNumero(valor);
  return n === null ? VAZIO : numeroCurto.format(n);
}

export function fmtDecimal(valor: number | string | null | undefined, casas = 1): string {
  const n = paraNumero(valor);
  return n === null ? VAZIO : n.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

export function fmtPercentual(valor: number | string | null | undefined, casas = 1): string {
  const n = paraNumero(valor);
  return n === null ? VAZIO : `${fmtDecimal(n, casas)}%`;
}

export function fmtMoeda(
  valor: number | string | null | undefined,
  moeda: string | null | undefined,
): string {
  const n = paraNumero(valor);
  if (n === null) return VAZIO;
  if (n === 0) return "Gratuito";
  return n.toLocaleString("pt-BR", {
    style: "currency",
    currency: moeda ?? "BRL",
  });
}

export function fmtDataHora(iso: string | null | undefined): string {
  return iso ? dataHora.format(paraData(iso)) : VAZIO;
}

export function fmtDataCurta(iso: string | null | undefined): string {
  return iso ? dataCurta.format(paraData(iso)) : VAZIO;
}

export function fmtData(iso: string | null | undefined): string {
  return iso ? paraData(iso).toLocaleDateString("pt-BR") : VAZIO;
}

/** Segundos -> "38min 12s"; a duracao de partida nunca chega a horas por aqui. */
export function fmtDuracao(segundos: number | null | undefined): string {
  if (segundos === null || segundos === undefined) return VAZIO;
  const minutos = Math.floor(segundos / 60);
  const resto = Math.round(segundos % 60);
  return `${minutos}min ${String(resto).padStart(2, "0")}s`;
}

export { VAZIO };

/**
 * Tempo decorrido em texto curto: "Há 15 seg", "Há 4 h", "Há 2 d".
 *
 * O desenho do Stitch mostra a idade da coleta, nao o carimbo dela: numa tela
 * de telemetria a pergunta e "isso esta fresco?", e um horario absoluto obriga
 * o leitor a fazer a subtracao de cabeca. O carimbo completo continua no
 * `title` do elemento, para quem precisar do valor exato.
 */
export function fmtRelativo(iso: string | null | undefined): string {
  if (!iso) return VAZIO;

  const segundos = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  const escalas: [limite: number, divisor: number, sufixo: string][] = [
    [60, 1, "seg"],
    [3600, 60, "min"],
    [86400, 3600, "h"],
    [2592000, 86400, "d"],
  ];

  for (const [limite, divisor, sufixo] of escalas) {
    if (segundos < limite) return `Há ${Math.floor(segundos / divisor)} ${sufixo}`;
  }
  return fmtData(iso);
}

/**
 * Classificacao da Steam traduzida e classificada em polaridade.
 *
 * A Steam devolve o rotulo em ingles ("Very Positive"); a tela inteira e em
 * portugues. A polaridade e o que decide a cor do chip - e ela sai do rotulo,
 * nao da nota numerica, porque e o rotulo que o usuario da Steam reconhece.
 */
export function classificacaoSteam(
  bruta: string | null | undefined,
): { texto: string; polaridade: "positiva" | "neutra" | "negativa" } | null {
  if (!bruta) return null;

  const mapa: Record<string, [string, "positiva" | "neutra" | "negativa"]> = {
    "overwhelmingly positive": ["Extremamente Positivas", "positiva"],
    "very positive": ["Muito Positivas", "positiva"],
    positive: ["Positivas", "positiva"],
    "mostly positive": ["Majoritariamente Positivas", "positiva"],
    mixed: ["Neutras", "neutra"],
    "mostly negative": ["Majoritariamente Negativas", "negativa"],
    negative: ["Negativas", "negativa"],
    "very negative": ["Muito Negativas", "negativa"],
    "overwhelmingly negative": ["Extremamente Negativas", "negativa"],
  };

  const achado = mapa[bruta.trim().toLowerCase()];
  // Rotulo desconhecido passa direto, sem cor: inventar polaridade seria pior
  // que nao ter nenhuma.
  return achado
    ? { texto: achado[0], polaridade: achado[1] }
    : { texto: bruta, polaridade: "neutra" };
}
