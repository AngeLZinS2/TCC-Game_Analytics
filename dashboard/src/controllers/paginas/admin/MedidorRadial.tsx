/**
 * Medidor radial (anel de progresso) — CPU / memória / disco da VPS.
 *
 * SVG escrito à mão, como todo gráfico do projeto (ver `AreaNeon`). O anel
 * de fundo é fixo; o anel colorido cresce de 0 até o percentual via
 * `strokeDashoffset` + `useEntrarNaTela`, com glow proporcional à cor — a
 * mesma receita do traço do `AreaNeon`, só que num círculo em vez de uma
 * curva. A cor muda com a gravidade (verde/âmbar/vermelho): a mesma leitura
 * que um operador de VPS já usa em qualquer painel de monitoramento.
 */

import { useId } from "react";

import { useEntrarNaTela } from "@models/hooks/animacao";
import { Icone } from "@views/componentes/base";

const RAIO = 50;
const CIRCUNFERENCIA = 2 * Math.PI * RAIO;

function corDaGravidade(percentual: number): string {
  if (percentual >= 90) return "#ff8a8a";
  if (percentual >= 70) return "#f3b13b";
  return "#40d19e";
}

export function MedidorRadial({
  rotulo,
  icone,
  percentual,
  detalhe,
}: {
  rotulo: string;
  icone: string;
  /** `null` quando a fonte não devolveu essa métrica. */
  percentual: number | null;
  detalhe: string;
}) {
  const id = useId().replace(/:/g, "");
  const entrou = useEntrarNaTela(percentual ?? -1);
  const p = Math.max(0, Math.min(100, percentual ?? 0));
  const cor = percentual === null ? "#4a505c" : corDaGravidade(p);
  const offset = CIRCUNFERENCIA * (1 - (entrou ? p : 0) / 100);

  return (
    <div className="flex flex-col items-center gap-space-sm rounded-lg bg-surface-container-lowest p-space-base transition-colors hover:bg-surface-container">
      <div className="relative h-28 w-28 shrink-0">
        <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90" aria-hidden>
          <circle
            cx="60"
            cy="60"
            r={RAIO}
            fill="none"
            stroke="currentColor"
            className="text-surface-container-highest"
            strokeWidth="10"
          />
          <defs>
            <linearGradient id={`medidor-${id}`} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={cor} stopOpacity="0.5" />
              <stop offset="100%" stopColor={cor} />
            </linearGradient>
          </defs>
          <circle
            cx="60"
            cy="60"
            r={RAIO}
            fill="none"
            stroke={`url(#medidor-${id})`}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={CIRCUNFERENCIA}
            strokeDashoffset={offset}
            style={{
              transition: "stroke-dashoffset 900ms cubic-bezier(0.16, 1, 0.3, 1)",
              filter: percentual === null ? undefined : `drop-shadow(0 0 5px ${cor}99)`,
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-headline-sm text-headline-sm tabular-nums text-on-surface">
            {percentual !== null ? `${Math.round(p)}%` : "—"}
          </span>
        </div>
      </div>

      <div className="flex flex-col items-center gap-space-xxs text-center">
        <span className="flex items-center gap-space-xxs font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <span style={{ color: cor }}>
            <Icone nome={icone} className="text-[14px]" />
          </span>
          {rotulo}
        </span>
        <span className="font-body-sm text-body-sm text-on-surface-variant">{detalhe}</span>
      </div>
    </div>
  );
}
