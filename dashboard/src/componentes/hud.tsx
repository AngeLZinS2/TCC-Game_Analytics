/**
 * Os blocos do "HUD" do desenho do Stitch.
 *
 * Sao os elementos que aparecem em varias telas com a mesma forma: o cartao de
 * KPI de tres colunas, as pilulas de ordenacao, os chips com contagem, a barra
 * de ranking com gradiente e o sparkline. Cada um e um porte direto do markup
 * gerado - as classes sao as mesmas.
 */

import type { ReactNode } from "react";

import { Icone } from "./base";

/** Acento de um bloco. O desenho alterna os tres entre os cartoes. */
export type Acento = "primaria" | "secundaria" | "terciaria";

const ACENTO: Record<Acento, { texto: string; ponto: string; brilho: string }> = {
  primaria: {
    texto: "text-primary",
    ponto: "bg-primary-container",
    brilho: "bg-primary-container/10",
  },
  secundaria: {
    texto: "text-secondary",
    ponto: "bg-secondary",
    brilho: "bg-secondary-container/15",
  },
  terciaria: {
    texto: "text-tertiary",
    ponto: "bg-tertiary-container",
    brilho: "bg-tertiary-container/10",
  },
};

/**
 * Sparkline: a forma da serie, sem eixo e sem rotulo.
 *
 * Nao usa Recharts de proposito. O que se le aqui e a silhueta, nao valores -
 * um grafico de verdade traria eixo, grade e tooltip que ninguem vai consultar
 * dentro de um cartao de 36px de altura. Os valores exatos estao na tela de
 * detalhe do jogo.
 */
export function Sparkline({
  valores,
  className = "text-primary-container",
}: {
  valores: number[];
  className?: string;
}) {
  // Um ponto so nao tem silhueta: dois pontos identicos desenhariam uma reta
  // horizontal, que sugere "estavel" quando o certo e "ainda nao da para ver".
  if (valores.length < 2) {
    return (
      <div className="flex h-9 items-center font-label-caps text-label-caps text-outline">
        série ainda com {valores.length === 1 ? "um ponto" : "nenhum ponto"}
      </div>
    );
  }

  const maximo = Math.max(...valores);
  const minimo = Math.min(...valores);
  const amplitude = maximo - minimo || 1;

  const pontos = valores.map((valor, indice) => {
    const x = (indice / (valores.length - 1)) * 200;
    const y = 32 - ((valor - minimo) / amplitude) * 28;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const linha = `M ${pontos.join(" L ")}`;

  return (
    <div className="mt-space-md flex h-9 w-full items-end">
      <svg
        className={`h-full w-full overflow-visible ${className}`}
        viewBox="0 0 200 36"
        preserveAspectRatio="none"
        aria-hidden
      >
        <path
          d={linha}
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="2.5"
          vectorEffect="non-scaling-stroke"
        />
        <path d={`${linha} L 200,36 L 0,36 Z`} fill="currentColor" opacity="0.08" />
      </svg>
    </div>
  );
}

/** Barras de segmento: quantos "blocos" de um total estao acesos. */
export function Segmentos({
  acesos,
  total = 6,
  acento = "secundaria",
}: {
  acesos: number;
  total?: number;
  acento?: Acento;
}) {
  return (
    <div
      className="mt-space-md grid gap-1 pt-2"
      style={{ gridTemplateColumns: `repeat(${total}, minmax(0, 1fr))` }}
      aria-hidden
    >
      {Array.from({ length: total }, (_, indice) => (
        <div
          key={indice}
          className={`h-2 rounded-sm ${
            indice < acesos ? ACENTO[acento].ponto : "bg-surface-container-highest"
          }`}
        />
      ))}
    </div>
  );
}

/**
 * O cartao de KPI do desenho: etiqueta tecnica em cima, numero grande, e um
 * indicador embaixo (sparkline, segmentos ou barra).
 */
export function KpiHud({
  etiqueta,
  canto,
  valor,
  rotulo,
  variacao,
  notaVariacao,
  acento = "primaria",
  children,
}: {
  /** A linha tecnica do topo, em caixa alta. */
  etiqueta: string;
  /** Texto do canto superior direito. */
  canto?: ReactNode;
  valor: ReactNode;
  rotulo: string;
  /** Variacao percentual. `null` quando ainda nao ha com o que comparar. */
  variacao?: number | null;
  notaVariacao?: string;
  acento?: Acento;
  /** O indicador do rodape: `Sparkline`, `Segmentos` ou o que a tela precisar. */
  children?: ReactNode;
}) {
  const cor = ACENTO[acento];
  const subiu = (variacao ?? 0) >= 0;

  return (
    <div className="group relative overflow-hidden rounded-xl bg-surface-container-low p-space-base shadow-lg transition-all hover:bg-surface-container">
      <div
        className={`pointer-events-none absolute right-0 top-0 h-28 w-28 rounded-full blur-2xl ${cor.brilho}`}
        aria-hidden
      />

      <div className="flex items-center justify-between font-label-caps text-label-caps text-outline">
        <div className="flex items-center gap-space-xs">
          <span className={`h-2 w-2 rounded ${cor.ponto}`} aria-hidden />
          <span>{etiqueta}</span>
        </div>
        {canto && (
          <span className={`font-title-code text-title-code ${cor.texto}`}>{canto}</span>
        )}
      </div>

      <div className="mt-space-md flex items-baseline justify-between gap-space-sm">
        <div className="flex min-w-0 flex-col">
          <span
            className={`font-headline-kpi text-headline-kpi tracking-tight ${cor.texto}`}
          >
            {valor}
          </span>
          <span className="font-title-code text-title-code text-on-surface-variant">
            {rotulo}
          </span>
        </div>

        <div className="flex shrink-0 flex-col items-end">
          {variacao === null || variacao === undefined ? (
            // Sem segunda coleta nao existe variacao. O desenho reserva o
            // espaco, entao ele fica ocupado por um travessao em vez de sumir e
            // desalinhar os tres cartoes.
            <span className="font-title-code text-title-code text-outline">—</span>
          ) : (
            <div
              className={`flex items-center gap-space-xxs rounded bg-surface-container-highest px-space-xs py-space-xxs ${
                subiu ? "text-tertiary" : "text-error"
              }`}
            >
              <Icone
                nome={subiu ? "arrow_upward" : "arrow_downward"}
                className="text-[16px]"
              />
              <span className="font-title-code text-title-code">
                {subiu ? "+" : ""}
                {variacao.toFixed(1)}%
              </span>
            </div>
          )}
          {notaVariacao && (
            <span className="mt-1 font-label-caps text-label-caps text-outline">
              {notaVariacao}
            </span>
          )}
        </div>
      </div>

      {children}
    </div>
  );
}

/** Pilula de ordenacao. A ativa recebe o brilho ciano do desenho. */
export function Pilula({
  ativa,
  aoClicar,
  icone,
  corIcone,
  desabilitada,
  titulo,
  children,
}: {
  ativa?: boolean;
  aoClicar?: () => void;
  icone?: string;
  corIcone?: string;
  desabilitada?: boolean;
  titulo?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={aoClicar}
      disabled={desabilitada}
      title={titulo}
      aria-pressed={ativa}
      className={[
        "flex items-center gap-space-xxs rounded px-space-sm py-space-xs font-title-code text-title-code transition-colors",
        desabilitada
          ? "cursor-not-allowed bg-surface-container/40 text-outline/50"
          : ativa
            ? "bg-primary-container text-on-primary shadow-[0_0_12px_rgba(0,229,255,0.35)]"
            : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface",
      ].join(" ")}
    >
      {icone && <Icone nome={icone} className={`text-[16px] ${corIcone ?? ""}`} />}
      {children}
    </button>
  );
}

/** Chip com contagem ao lado - a sub-barra de generos. */
export function ChipContagem({
  ativo,
  aoClicar,
  contagem,
  cor,
  children,
}: {
  ativo?: boolean;
  aoClicar?: () => void;
  contagem?: number;
  /** Ponto colorido a esquerda, quando o item tem cor propria. */
  cor?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={aoClicar}
      aria-pressed={ativo}
      className={[
        "flex shrink-0 items-center gap-space-xs rounded px-space-sm py-space-xs font-title-code text-title-code transition-colors",
        ativo
          ? "bg-surface-container-high text-primary shadow-[0_0_8px_rgba(0,229,255,0.2)]"
          : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface",
      ].join(" ")}
    >
      {cor && (
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: cor }}
          aria-hidden
        />
      )}
      <span>{children}</span>
      {contagem !== undefined && (
        <span
          className={`rounded px-space-xs font-label-caps text-label-caps ${
            ativo ? "bg-surface-container-lowest text-primary" : "text-outline"
          }`}
        >
          {contagem}
        </span>
      )}
    </button>
  );
}

/**
 * Uma linha do ranking: posicao, etiqueta, nome, variacao, valor e a barra.
 *
 * A barra e CSS, nao Recharts. O desenho pede gradiente, brilho e cantos
 * arredondados numa barra que ocupa a largura toda do bloco - e um elemento de
 * layout, nao um sistema de coordenadas. Trazer uma biblioteca de grafico para
 * desenhar um retangulo custaria mais do que resolve.
 */
export function BarraRanking({
  posicao,
  etiqueta,
  corEtiqueta,
  nome,
  valor,
  variacao,
  proporcao,
  aoClicar,
}: {
  posicao: number;
  etiqueta?: string;
  corEtiqueta?: string;
  nome: string;
  valor: ReactNode;
  variacao?: number | null;
  /** 0 a 1, relativo ao maior do ranking. */
  proporcao: number;
  aoClicar?: () => void;
}) {
  const conteudo = (
    <>
      <div className="flex items-center justify-between gap-space-sm font-title-code text-body-sm">
        <div className="flex min-w-0 items-center gap-space-sm">
          <span className="w-6 shrink-0 font-label-caps text-label-caps text-outline">
            #{String(posicao).padStart(2, "0")}
          </span>
          {etiqueta && (
            <span
              className="shrink-0 rounded bg-surface-container-highest px-space-xs py-space-xxs font-badge-status text-badge-status uppercase"
              style={{ color: corEtiqueta }}
            >
              {etiqueta}
            </span>
          )}
          <span className="truncate font-bold text-on-surface">{nome}</span>
        </div>

        <div className="flex shrink-0 items-center gap-space-md">
          {variacao !== null && variacao !== undefined && (
            <span
              className={`flex items-center gap-space-xxs ${
                variacao >= 0 ? "text-tertiary" : "text-error"
              }`}
            >
              <Icone
                nome={variacao >= 0 ? "arrow_drop_up" : "arrow_drop_down"}
                className="text-[14px]"
              />
              {variacao >= 0 ? "+" : ""}
              {variacao.toFixed(1)}%
            </span>
          )}
          <span className="font-headline-sm text-headline-sm text-primary">{valor}</span>
        </div>
      </div>

      <div className="flex h-3 w-full overflow-hidden rounded-full bg-surface-container-lowest">
        <div
          className="h-full rounded-full bg-gradient-to-r from-primary-container via-primary to-secondary shadow-[0_0_10px_rgba(0,229,255,0.5)] transition-all duration-700"
          style={{ width: `${Math.max(2, proporcao * 100).toFixed(1)}%` }}
        />
      </div>
    </>
  );

  const classe =
    "flex w-full flex-col gap-space-xxs rounded bg-surface-container p-space-sm text-left transition-colors hover:bg-surface-container-high";

  return aoClicar ? (
    <button type="button" onClick={aoClicar} className={classe}>
      {conteudo}
    </button>
  ) : (
    <div className={classe}>{conteudo}</div>
  );
}

/**
 * Barra de duas cores que soma 100% - o winrate de um lado contra o outro.
 *
 * Duas cores porque a pergunta e de polaridade ("quem leva vantagem?"), e uma
 * barra unica com rotulo obrigaria a fazer 100 menos o valor de cabeca.
 */
export function BarraSegmentada({
  fracaoA,
  corA = "bg-tertiary-container",
  corB = "bg-error",
  legendaEsquerda,
  legendaDireita,
}: {
  /** 0 a 1. O resto vai para o lado B. */
  fracaoA: number;
  corA?: string;
  corB?: string;
  legendaEsquerda?: ReactNode;
  legendaDireita?: ReactNode;
}) {
  const a = Math.min(100, Math.max(0, fracaoA * 100));

  return (
    <div className="flex w-full flex-col gap-space-xs">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-surface-container-highest">
        <div className={`h-full ${corA}`} style={{ width: `${a}%` }} />
        <div className={`h-full ${corB}`} style={{ width: `${100 - a}%` }} />
      </div>
      {(legendaEsquerda || legendaDireita) && (
        <div className="flex items-center justify-between text-outline">
          <span className="font-label-caps text-label-caps">{legendaEsquerda}</span>
          <span className="font-badge-status text-badge-status text-primary">
            {legendaDireita}
          </span>
        </div>
      )}
    </div>
  );
}

/**
 * Rodape de paginacao do desenho: quantas linhas, os numeros e as setas.
 *
 * Renderiza mesmo com uma pagina so - o desenho reserva a faixa, e some-la
 * mudaria a altura da tela conforme o volume de dado.
 */
export function Paginacao({
  pagina,
  totalPaginas,
  porPagina,
  opcoesPorPagina = [10, 25, 50, 100],
  aoMudarPagina,
  aoMudarPorPagina,
  resumo,
}: {
  /** Base 1. */
  pagina: number;
  totalPaginas: number;
  porPagina: number;
  opcoesPorPagina?: number[];
  aoMudarPagina: (pagina: number) => void;
  aoMudarPorPagina: (quantidade: number) => void;
  resumo?: ReactNode;
}) {
  // Janela de no maximo 5 numeros em volta da pagina atual: com 148 paginas,
  // listar todas empurraria o resto da faixa para fora da tela.
  const inicio = Math.max(1, Math.min(pagina - 2, totalPaginas - 4));
  const numeros = Array.from(
    { length: Math.min(5, totalPaginas) },
    (_, indice) => inicio + indice,
  ).filter((n) => n >= 1 && n <= totalPaginas);

  return (
    <div className="flex flex-wrap items-center justify-between gap-space-base pt-space-sm">
      <div className="flex items-center gap-space-sm font-label-caps text-label-caps uppercase tracking-widest text-outline">
        <span>{resumo}</span>
        <label className="flex items-center gap-space-xs">
          Linhas por página
          <select
            value={porPagina}
            onChange={(evento) => aoMudarPorPagina(Number(evento.target.value))}
            className="rounded bg-surface-container px-space-xs py-space-xxs font-title-code text-title-code text-on-surface outline-none"
          >
            {opcoesPorPagina.map((opcao) => (
              <option key={opcao} value={opcao}>
                {opcao}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex items-center gap-space-xxs">
        <button
          type="button"
          onClick={() => aoMudarPagina(pagina - 1)}
          disabled={pagina <= 1}
          aria-label="Página anterior"
          className="rounded bg-surface-container p-space-xs text-on-surface-variant transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Icone nome="chevron_left" className="text-[18px]" />
        </button>

        {numeros.map((numero) => (
          <button
            key={numero}
            type="button"
            onClick={() => aoMudarPagina(numero)}
            aria-current={numero === pagina ? "page" : undefined}
            className={`min-w-8 rounded px-space-xs py-space-xxs font-title-code text-title-code transition-colors ${
              numero === pagina
                ? "bg-primary-container text-on-primary"
                : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high"
            }`}
          >
            {numero}
          </button>
        ))}

        {totalPaginas > numeros.at(-1)! && (
          <>
            <span className="px-space-xxs text-outline">…</span>
            <button
              type="button"
              onClick={() => aoMudarPagina(totalPaginas)}
              className="min-w-8 rounded bg-surface-container px-space-xs py-space-xxs font-title-code text-title-code text-on-surface-variant transition-colors hover:bg-surface-container-high"
            >
              {totalPaginas}
            </button>
          </>
        )}

        <button
          type="button"
          onClick={() => aoMudarPagina(pagina + 1)}
          disabled={pagina >= totalPaginas}
          aria-label="Próxima página"
          className="rounded bg-surface-container p-space-xs text-on-surface-variant transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Icone nome="chevron_right" className="text-[18px]" />
        </button>
      </div>
    </div>
  );
}

/**
 * Cartao de secao no idioma do desenho: icone + titulo em caixa alta a
 * esquerda, meta a direita, corpo abaixo.
 *
 * E o `Cartao` do `base.tsx` com a moldura que o Stitch usa nas telas de
 * telemetria - titulo maior, cantos `rounded-xl` e sombra mais forte.
 */
export function Painel({
  icone,
  titulo,
  descricao,
  meta,
  className = "",
  children,
}: {
  icone?: string;
  titulo: ReactNode;
  descricao?: ReactNode;
  meta?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={`space-y-space-md rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl ${className}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-space-sm">
        <div className="min-w-0">
          <h2 className="flex items-center gap-space-xs font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
            {icone && <Icone nome={icone} className="text-[22px] text-primary" />}
            {titulo}
          </h2>
          {descricao && (
            <p className="mt-space-xxs font-body-sm text-body-sm text-outline">
              {descricao}
            </p>
          )}
        </div>
        {meta && <div className="flex shrink-0 items-center gap-space-xs">{meta}</div>}
      </div>
      {children}
    </section>
  );
}


/**
 * Estilo unico dos `<select>` e `<input>` das barras de filtro.
 *
 * Fica como string e nao como componente porque os campos aparecem com
 * estruturas diferentes em cada tela - o que se compartilha e a aparencia, nao
 * a marcacao em volta.
 */
export const CAMPO =
  "rounded bg-surface-container px-space-md py-space-xs font-title-code text-title-code text-on-surface " +
  "border border-outline-variant/40 outline-none transition-colors " +
  "hover:border-outline focus:border-primary-container disabled:cursor-not-allowed disabled:text-outline/60";
