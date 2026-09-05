/**
 * O resultado da resposta em forma de dado, nao de conversa.
 *
 * O numero grande e o `itens[0]` da serie que o backend devolveu - ordenada em
 * SQL, no mesmo SELECT que escreveu o bloco de contexto. A tela nao escolhe o
 * lider nem le o texto do modelo para descobrir quem venceu: ela mostra a
 * primeira linha do ranking que ja chegou pronta.
 *
 * Sem serie, este cartao nao aparece. Nao existe versao "aproximada" dele.
 */

import type { SerieAssistente } from "../../api/tipos";
import { Icone } from "../../componentes/base";
import { useContagem, useEntrarNaTela } from "../../hooks/animacao";
import { fmtCurto, fmtDecimal } from "../../utilitarios/formatos";

function formatar(valor: number, unidade: string): string {
  if (unidade === "%") return `${fmtDecimal(valor)}%`;
  return fmtCurto(valor);
}

export function CartaoResultado({
  serie,
  pergunta,
}: {
  serie: SerieAssistente;
  pergunta: string;
}) {
  const [lider, ...demais] = serie.itens;
  if (!lider) return null;

  const maximo = Math.max(...serie.itens.map((i) => i.valor), 1);

  return (
    <div className="flex flex-col gap-space-base">
      <div className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-primary">
        <span aria-hidden>✦</span> Resultado
      </div>

      {/* A pergunta acima do numero: sem ela, "94,1%" sozinho nao diz de que. */}
      <p className="font-body-sm text-body-sm text-outline">{pergunta}</p>

      <Lider ponto={lider} unidade={serie.unidade} proporcao={lider.valor / maximo} />

      {demais.length > 0 && (
        <ol className="flex flex-col divide-y divide-outline-variant/20 border-t border-outline-variant/20">
          {demais.map((ponto, indice) => (
            <li
              key={ponto.rotulo}
              className="flex items-center gap-space-sm py-space-sm font-title-code text-title-code"
            >
              <span className="w-5 shrink-0 text-center text-outline tabular-nums">
                {indice + 2}
              </span>
              <span className="min-w-0 flex-1 truncate text-on-surface">{ponto.rotulo}</span>
              {ponto.detalhe && (
                <span className="hidden shrink-0 text-outline sm:inline">{ponto.detalhe}</span>
              )}
              <span className="shrink-0 tabular-nums text-on-surface-variant">
                {formatar(ponto.valor, serie.unidade)}
              </span>
            </li>
          ))}
        </ol>
      )}

      <p className="flex items-center gap-space-xs border-t border-outline-variant/20 pt-space-sm font-badge-status text-badge-status uppercase tracking-wider text-outline">
        <Icone nome="database" className="text-[14px]" />
        {serie.itens.length} {serie.itens.length === 1 ? "item" : "itens"} · {serie.titulo}
      </p>
    </div>
  );
}

/** O primeiro colocado: numero grande, barra proporcional e o detalhe da fonte. */
function Lider({
  ponto,
  unidade,
  proporcao,
}: {
  ponto: { rotulo: string; valor: number; detalhe: string | null };
  unidade: string;
  proporcao: number;
}) {
  // Conta ate o valor em vez de aparecer pronto - mesmo tratamento dos KPIs
  // das outras telas, para o numero principal ter o mesmo peso visual.
  const valor = useContagem(ponto.valor);
  const entrou = useEntrarNaTela(ponto.rotulo);

  return (
    <div className="flex items-start gap-space-base">
      <span
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-container/15 font-title-code text-title-code text-primary ring-1 ring-primary/40"
        aria-hidden
      >
        1
      </span>

      <div className="min-w-0 flex-1">
        <h3 className="truncate font-headline-lg text-headline-lg text-on-surface">
          {ponto.rotulo}
        </h3>
        <div className="font-headline-kpi text-headline-kpi leading-none text-primary drop-shadow-[0_0_16px_rgba(0,229,255,0.35)]">
          {formatar(valor ?? ponto.valor, unidade)}
        </div>
        <div className="mt-space-xxs font-label-caps text-label-caps uppercase tracking-widest text-outline">
          {ponto.detalhe ?? unidade}
        </div>

        <div className="mt-space-sm h-1.5 w-full overflow-hidden rounded-full bg-surface-container-lowest">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary-container to-primary"
            style={{
              width: `${entrou ? Math.max(2, proporcao * 100) : 0}%`,
              transition: "width 700ms cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          />
        </div>
      </div>
    </div>
  );
}
