/**
 * Blocos visuais reutilizados por todas as telas.
 *
 * As classes saem direto do desenho do Stitch: o chanfro de canto
 * (`clip-path`), a tipografia `label-caps` / `headline-kpi` e os tokens de
 * superficie sao o vocabulario do design system "Apex Broadcast Engine".
 */

import type { ReactNode } from "react";

import { ErroApi } from "../api/cliente";

/**
 * O chanfro do canto superior direito dos cartoes de KPI.
 *
 * Fica numa constante porque e o detalhe que mais se repete no desenho, e
 * porque escrever `polygon(...)` a mao em cada cartao e onde o valor erra.
 */
export const CHANFRO =
  "[clip-path:polygon(0_0,calc(100%-14px)_0,100%_14px,100%_100%,0_100%)]";

export function Icone({
  nome,
  className = "text-[18px]",
}: {
  nome: string;
  className?: string;
}) {
  // aria-hidden: o icone sempre acompanha um rotulo em texto; anunciar o nome
  // da ligadura ("space_dashboard") so poluiria o leitor de tela.
  return (
    <span className={`material-symbols-outlined ${className}`} aria-hidden>
      {nome}
    </span>
  );
}

export function Cartao({
  titulo,
  descricao,
  icone,
  acoes,
  className = "",
  children,
}: {
  titulo?: ReactNode;
  descricao?: ReactNode;
  icone?: string;
  acoes?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={`bg-surface-container-low/90 rounded shadow-xl overflow-hidden ${className}`}
    >
      {(titulo || acoes) && (
        <header className="flex items-start justify-between gap-space-base border-b border-outline-variant/40 px-space-lg py-space-md">
          <div className="min-w-0">
            {titulo && (
              <h2 className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-on-surface-variant">
                {icone && <Icone nome={icone} className="text-[16px] text-primary" />}
                {titulo}
              </h2>
            )}
            {descricao && (
              <p className="mt-space-xxs font-body-sm text-body-sm text-outline">
                {descricao}
              </p>
            )}
          </div>
          {acoes && <div className="flex shrink-0 items-center gap-space-xs">{acoes}</div>}
        </header>
      )}
      <div className="p-space-lg">{children}</div>
    </section>
  );
}

/** Direcao de uma variacao: define a cor do selo, nunca so a seta. */
type Tendencia = "alta" | "baixa" | "neutra";

export function Kpi({
  rotulo,
  valor,
  icone,
  nota,
  tendencia = "neutra",
  rodape,
}: {
  rotulo: string;
  valor: ReactNode;
  icone?: string;
  nota?: ReactNode;
  tendencia?: Tendencia;
  rodape?: ReactNode;
}) {
  const selo = {
    alta: "bg-tertiary/10 text-tertiary",
    baixa: "bg-error/10 text-error",
    neutra: "bg-surface-container-highest text-on-surface-variant",
  }[tendencia];

  const seta = { alta: "arrow_upward", baixa: "arrow_downward", neutra: "remove" }[
    tendencia
  ];

  return (
    <div
      className={`relative bg-surface-container-low/90 p-space-lg rounded shadow-xl overflow-hidden ${CHANFRO}`}
    >
      <div
        className="absolute -top-12 -right-12 h-32 w-32 rounded-full bg-primary-container/10 blur-2xl pointer-events-none"
        aria-hidden
      />

      <div className="flex items-center justify-between gap-space-xs">
        <span className="font-label-caps text-label-caps uppercase tracking-wider text-outline">
          {rotulo}
        </span>
        {icone && <Icone nome={icone} className="text-[18px] text-primary" />}
      </div>

      <div className="mt-space-sm font-headline-kpi text-headline-kpi tracking-tight text-on-surface">
        {valor}
      </div>

      {(nota || rodape) && (
        <div className="mt-space-xs flex items-center justify-between gap-space-xs">
          {nota ? (
            <span
              className={`inline-flex items-center gap-space-xxs rounded px-space-xs py-space-xxs ${selo}`}
            >
              <Icone nome={seta} className="text-[14px]" />
              <span className="font-badge-status text-badge-status">{nota}</span>
            </span>
          ) : (
            <span />
          )}
          {rodape && (
            <span className="font-body-sm text-body-sm text-outline">{rodape}</span>
          )}
        </div>
      )}
    </div>
  );
}

export function Selo({
  children,
  cor = "neutro",
  className = "",
}: {
  children: ReactNode;
  cor?: "primario" | "positivo" | "negativo" | "neutro";
  className?: string;
}) {
  const cores = {
    primario: "bg-primary-container/15 text-primary",
    positivo: "bg-tertiary/10 text-tertiary",
    negativo: "bg-error/10 text-error",
    neutro: "bg-surface-container-highest text-on-surface-variant",
  }[cor];

  return (
    <span
      className={`inline-flex items-center gap-space-xxs rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase ${cores} ${className}`}
    >
      {children}
    </span>
  );
}

export function Aviso({ children }: { children: ReactNode }) {
  return (
    <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
      {children}
    </p>
  );
}

export function Esqueleto({ altura = 220 }: { altura?: number }) {
  return (
    <div
      className="animate-pulse rounded bg-surface-container-high/60"
      style={{ height: altura }}
      aria-hidden
    />
  );
}

export function MensagemErro({ erro }: { erro: unknown }) {
  const detalhe =
    erro instanceof ErroApi
      ? erro.detalhe
      : erro instanceof Error
        ? erro.message
        : "Erro desconhecido.";

  return (
    <div
      className="flex items-start gap-space-sm rounded border border-error/30 bg-error/10 px-space-base py-space-md text-error"
      role="alert"
    >
      <Icone nome="error" className="mt-[2px] text-[18px]" />
      <div>
        <strong className="block font-headline-sm text-headline-sm">
          Não deu para carregar estes dados.
        </strong>
        <span className="font-body-sm text-body-sm text-on-surface-variant">
          {detalhe}
        </span>
      </div>
    </div>
  );
}

/**
 * Envelope padrao de uma consulta: esqueleto na primeira carga, erro, vazio, ou
 * o conteudo. Em refetch o conteudo anterior fica visivel mais apagado - piscar
 * um esqueleto a cada troca de filtro causa salto de layout.
 */
export function Consulta<T>({
  estado,
  vazio = "Nenhum dado coletado ainda.",
  altura,
  children,
}: {
  estado: {
    data: T | undefined;
    isPending: boolean;
    isError: boolean;
    error: unknown;
    isFetching: boolean;
  };
  vazio?: ReactNode;
  altura?: number;
  children: (dados: T) => ReactNode;
}) {
  if (estado.isPending) return <Esqueleto altura={altura} />;
  if (estado.isError) return <MensagemErro erro={estado.error} />;
  if (estado.data === undefined) return <Aviso>{vazio}</Aviso>;

  const semDados = Array.isArray(estado.data) && estado.data.length === 0;
  if (semDados) return <Aviso>{vazio}</Aviso>;

  return (
    <div className={estado.isFetching ? "opacity-60 transition-opacity" : undefined}>
      {children(estado.data)}
    </div>
  );
}

export function Etiquetas({ itens, maximo }: { itens: string[]; maximo?: number }) {
  if (itens.length === 0) {
    return <span className="text-outline">—</span>;
  }

  // Numa celula de tabela, cinco generos empilham a linha em tres andares; o
  // resto vira "+N" e o valor completo continua na pagina do jogo.
  const visiveis = maximo ? itens.slice(0, maximo) : itens;
  const restantes = itens.length - visiveis.length;

  return (
    <span className="flex flex-wrap gap-space-xxs">
      {visiveis.map((item) => (
        <span
          key={item}
          className="rounded bg-surface-container-highest px-space-xs py-space-xxs font-body-sm text-body-sm text-on-surface-variant"
        >
          {item}
        </span>
      ))}
      {restantes > 0 && (
        <span className="rounded bg-surface-container-highest px-space-xs py-space-xxs font-body-sm text-body-sm text-outline">
          +{restantes}
        </span>
      )}
    </span>
  );
}

/** Legenda textual: identidade nunca fica so na cor. */
export function Legenda({ itens }: { itens: { cor: string; rotulo: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-space-base font-body-sm text-body-sm text-on-surface-variant">
      {itens.map((item) => (
        <span key={item.rotulo} className="inline-flex items-center gap-space-xs">
          <i
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ background: item.cor }}
            aria-hidden
          />
          {item.rotulo}
        </span>
      ))}
    </div>
  );
}

export function Botao({
  children,
  icone,
  aoClicar,
  desabilitado,
  variante = "secundario",
  className = "",
}: {
  children: ReactNode;
  icone?: string;
  aoClicar?: () => void;
  desabilitado?: boolean;
  variante?: "primario" | "secundario";
  className?: string;
}) {
  const cores =
    variante === "primario"
      ? "bg-primary-container text-on-primary hover:brightness-110"
      : "bg-surface-container text-primary hover:bg-surface-container-high";

  return (
    <button
      type="button"
      onClick={aoClicar}
      disabled={desabilitado}
      className={`inline-flex items-center gap-space-xs rounded px-space-md py-space-xs font-title-code text-title-code shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${cores} ${className}`}
    >
      {icone && <Icone nome={icone} className="text-[18px]" />}
      {children}
    </button>
  );
}
