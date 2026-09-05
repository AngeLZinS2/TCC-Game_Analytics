/**
 * O que aparece enquanto a resposta nao voltou.
 *
 * O desenho pedia etapas marcando ✓ uma a uma. A tela nao pode fazer isso com
 * honestidade: a pergunta e UM POST - do lado do navegador so se sabe que ela
 * saiu e ainda nao voltou. Marcar "recuperando contexto ✓" num cronometro
 * seria animacao fingindo telemetria.
 *
 * Entao o unico ✓ e o que de fato se sabe (a pergunta saiu daqui), e as outras
 * etapas ficam em andamento, com a nota do que realmente demora.
 */

import { Icone } from "../../componentes/base";

const ETAPAS: { rotulo: string; detalhe: string }[] = [
  { rotulo: "Pergunta enviada", detalhe: "POST /api/assistente/perguntar" },
  { rotulo: "Blocos escolhidos", detalhe: "pela pergunta, no Python" },
  { rotulo: "Contexto montado", detalhe: "SQL escrito à mão" },
  { rotulo: "Resposta redigida", detalhe: "provedor externo" },
];

export function Processando() {
  return (
    <div className="flex flex-col gap-space-base rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl">
      <div className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-primary">
        <span className="animate-pulse" aria-hidden>
          ✦
        </span>
        Analisando seus dados…
      </div>

      <ol className="flex flex-col gap-space-sm" aria-live="polite">
        {ETAPAS.map((etapa, indice) => {
          const concluida = indice === 0;
          return (
            <li key={etapa.rotulo} className="flex items-center gap-space-sm">
              {concluida ? (
                <Icone nome="check_circle" className="text-[16px] text-tertiary" />
              ) : (
                <span
                  className="h-4 w-4 shrink-0 animate-pulse rounded-full ring-1 ring-outline-variant/60"
                  style={{ animationDelay: `${indice * 200}ms` }}
                  aria-hidden
                />
              )}
              <span
                className={`font-title-code text-title-code ${
                  concluida ? "text-on-surface" : "text-outline"
                }`}
              >
                {etapa.rotulo}
              </span>
              <span className="font-badge-status text-badge-status uppercase tracking-wider text-outline/70">
                {etapa.detalhe}
              </span>
            </li>
          );
        })}
      </ol>

      {/* Esqueleto do formato que vai chegar: cartao de resultado + gráfico. */}
      <div className="grid grid-cols-1 gap-space-base lg:grid-cols-2">
        <div className="h-48 animate-pulse rounded-lg bg-surface-container-high/50" />
        <div className="h-48 animate-pulse rounded-lg bg-surface-container-high/50 [animation-delay:150ms]" />
      </div>

      <p className="font-body-sm text-body-sm text-outline">
        O contexto sai do banco em milissegundos — o que demora é a resposta do
        provedor.
      </p>
    </div>
  );
}
