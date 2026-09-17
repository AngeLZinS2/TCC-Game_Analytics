/**
 * Status dos serviços internos — frescor por fonte de coleta.
 *
 * **Por que não tem coluna de latência.** O painel de referência pedia
 * "API PlayDB 42ms, Banco 8ms, Esports 120ms". Deste trio, só a do banco é
 * mensurável neste projeto: não existe medição de tempo de resposta de API
 * em lugar nenhum — nem tabela, nem coluna, nem coletor que registre isso.
 * Preencher a coluna com números plausíveis seria exatamente o tipo de
 * enfeite que este painel existe para não ter.
 *
 * O que o banco sabe de verdade é QUANDO cada fonte entregou dado pela
 * última vez, e qual é a cadência esperada dela. Isso responde a pergunta
 * que realmente importa na operação — "alguma coisa parou de coletar?" —,
 * que a latência sozinha nem responderia.
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import type { SaudeServicos, ServicoColeta } from "@models/api/tipos";
import { Icone } from "@views/componentes/base";
import { Painel } from "@views/componentes/hud";
import { fmtRelativo } from "@util/formatos";

const CORES: Record<string, string> = {
  ok: "text-tertiary",
  atrasado: "text-secondary",
  parado: "text-error",
  sem_cadencia: "text-outline",
};

const PONTOS: Record<string, string> = {
  ok: "bg-tertiary-container",
  atrasado: "bg-secondary-fixed-dim",
  parado: "bg-error",
  sem_cadencia: "bg-outline",
};

function Cadencia({ minutos }: { minutos: number | null }) {
  const { t } = useTranslation();
  if (minutos === null) return <span className="text-outline">—</span>;
  if (minutos >= 1440) return <>{t("admin.servicos.aCadaDias", { n: Math.round(minutos / 1440) })}</>;
  if (minutos >= 60) return <>{t("admin.servicos.aCadaHoras", { n: Math.round(minutos / 60) })}</>;
  return <>{t("admin.servicos.aCadaMin", { n: minutos })}</>;
}

export function PainelServicos({ dados }: { dados: SaudeServicos }) {
  const { t } = useTranslation();
  const [mostrarTudo, setMostrarTudo] = useState(false);

  // As que precisam de atenção já vêm primeiro do backend. Colapsar as
  // saudáveis é o que deixa o painel útil com 24 fontes: quem opera quer ver
  // o que está fora do lugar, não uma lista de 24 linhas verdes.
  const problemas = useMemo(
    () => dados.servicos.filter((s) => s.status === "parado" || s.status === "atrasado"),
    [dados.servicos],
  );
  const visiveis = mostrarTudo ? dados.servicos : dados.servicos.slice(0, Math.max(problemas.length, 6));

  return (
    <Painel
      icone="lan"
      titulo={t("admin.servicos.titulo")}
      descricao={t("admin.servicos.descricao")}
      meta={
        <span className="inline-flex items-center gap-space-xs font-badge-status text-badge-status uppercase text-on-surface-variant">
          <Icone nome="database" className="text-[13px] text-primary" />
          {dados.banco_latencia_ms === null
            ? t("admin.servicos.bancoSemResposta")
            : t("admin.servicos.bancoLatencia", { ms: dados.banco_latencia_ms })}
        </span>
      }
    >
      {/* Quando MUITAS fontes param juntas, a causa quase nunca são as APIs
          de terceiros: é o agendador desligado. O painel diz isso em vez de
          deixar quem lê concluir que meio mundo caiu ao mesmo tempo. */}
      {dados.fontes_paradas >= 3 && (
        <p className="flex items-start gap-space-xs rounded-lg bg-secondary-container/20 px-space-base py-space-sm font-body-md text-body-sm text-secondary">
          <Icone nome="info" className="mt-[2px] shrink-0 text-[15px]" />
          {t("admin.servicos.muitasParadas", {
            n: dados.fontes_paradas,
            total: dados.fontes_total,
          })}
        </p>
      )}

      <div className="rolagem-discreta overflow-x-auto rounded-lg">
        <table className="w-full min-w-[520px] border-collapse text-left">
          <thead>
            <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
              <th className="px-space-md py-space-sm">{t("admin.servicos.fonte")}</th>
              <th className="px-space-md py-space-sm">{t("admin.servicos.status")}</th>
              <th className="px-space-md py-space-sm text-right">{t("admin.servicos.ultimaColeta")}</th>
              <th className="px-space-md py-space-sm text-right">{t("admin.servicos.cadencia")}</th>
            </tr>
          </thead>
          <tbody>
            {visiveis.map((servico: ServicoColeta, indice) => (
              <tr
                key={servico.fonte}
                className={`transition-colors hover:bg-surface-container ${
                  indice % 2 ? "bg-[#131824]" : "bg-[#10141D]"
                }`}
              >
                <td className="px-space-md py-space-sm font-title-code text-title-code text-on-surface">
                  {servico.fonte}
                </td>
                <td className="px-space-md py-space-sm">
                  <span
                    className={`inline-flex items-center gap-space-xs font-badge-status text-badge-status uppercase ${CORES[servico.status] ?? "text-outline"}`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${PONTOS[servico.status] ?? "bg-outline"}`}
                      aria-hidden
                    />
                    {t(`admin.servicos.estado.${servico.status}`)}
                  </span>
                </td>
                <td className="px-space-md py-space-sm text-right font-body-md text-body-sm tabular-nums text-on-surface-variant">
                  {servico.ultima_coleta ? fmtRelativo(servico.ultima_coleta) : "—"}
                </td>
                <td className="px-space-md py-space-sm text-right font-body-md text-body-sm tabular-nums text-outline">
                  <Cadencia minutos={servico.intervalo_minutos} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dados.servicos.length > visiveis.length && (
        <button
          type="button"
          onClick={() => setMostrarTudo(true)}
          className="w-full rounded-lg bg-surface-container-high py-space-sm font-label-caps text-label-caps uppercase tracking-widest text-on-surface-variant transition-colors hover:bg-surface-container-highest"
        >
          {t("admin.servicos.verTodas", { n: dados.servicos.length })}
        </button>
      )}
    </Painel>
  );
}
