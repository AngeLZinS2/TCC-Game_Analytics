/**
 * Tooltip compartilhado dos graficos.
 *
 * O tooltip enriquece, nunca e o unico caminho para um valor: toda tela tem a
 * tabela equivalente. O foco por teclado nas linhas da tabela mostra o mesmo
 * que o hover no grafico.
 */

import type { ReactNode } from "react";

export interface LinhaDica {
  rotulo: string;
  valor: ReactNode;
}

interface Props<T> {
  /** Injetado pelo Recharts. */
  active?: boolean;
  payload?: { payload: T }[];
  titulo: (dado: T) => ReactNode;
  linhas: (dado: T) => LinhaDica[];
}

export function Dica<T>({ active, payload, titulo, linhas }: Props<T>) {
  if (!active || !payload?.length) return null;
  const dado = payload[0].payload;

  return (
    <div className="min-w-[180px] rounded border border-outline-variant/50 bg-surface-container-lowest/95 px-space-md py-space-sm shadow-xl backdrop-blur-sm">
      <div className="mb-space-xs font-label-caps text-label-caps uppercase tracking-widest text-primary">
        {titulo(dado)}
      </div>
      {linhas(dado).map((linha) => (
        <div
          className="flex items-baseline justify-between gap-space-base py-space-xxs"
          key={linha.rotulo}
        >
          <span className="font-body-sm text-body-sm text-on-surface-variant">
            {linha.rotulo}
          </span>
          <b className="font-title-code text-title-code tabular-nums text-on-surface">
            {linha.valor}
          </b>
        </div>
      ))}
    </div>
  );
}
