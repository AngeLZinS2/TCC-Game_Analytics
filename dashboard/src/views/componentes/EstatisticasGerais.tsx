/**
 * O painel "Estatísticas gerais" ao lado do título do catálogo.
 *
 * São números de cobertura da nossa base — quantos jogos existem na dimensão,
 * quantos têm telemetria na janela mais recente, quantos jogadores o último
 * snapshot somou — e não métricas da Steam inteira. Os rótulos dizem isso,
 * porque "4,5 milhões de jogadores" sem contexto seria lido como o número da
 * plataforma, que é outro (e mora na Visão Geral).
 */

import type { ReactNode } from "react";

import { Icone } from "@views/componentes/base";

export function CaixaEstatistica({
  icone,
  valor,
  rotulo,
  acento = "text-primary",
}: {
  icone: string;
  valor: ReactNode;
  rotulo: string;
  acento?: string;
}) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-space-sm rounded-xl bg-surface-container-lowest/70 px-space-sm py-space-xs ring-1 ring-outline-variant/25">
      <span
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-container/15 ${acento}`}
      >
        <Icone nome={icone} className="text-[18px]" />
      </span>
      <span className="flex min-w-0 flex-col leading-tight">
        <span className="truncate font-headline-sm text-headline-sm font-bold tabular-nums text-on-surface">
          {valor}
        </span>
        <span className="truncate font-label-caps text-label-caps text-outline">{rotulo}</span>
      </span>
    </div>
  );
}

export function EstatisticasGerais({
  titulo,
  children,
}: {
  titulo: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-label={titulo}
      className="flex min-w-0 flex-col gap-space-sm rounded-xl bg-surface-container-low/60 p-space-base ring-1 ring-outline-variant/20 backdrop-blur-sm"
    >
      <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
        {titulo}
      </span>
      <div className="flex flex-wrap gap-space-xs">{children}</div>
    </section>
  );
}
