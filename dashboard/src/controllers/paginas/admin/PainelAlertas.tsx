/**
 * Alertas — só problema real, derivado dos dados que já estão na tela.
 *
 * Não há endpoint de alertas nem tabela de incidentes neste projeto, e não
 * faria sentido criar um: tudo que caracteriza um problema aqui já está nas
 * respostas de `/sistema`, `/servicos` e `/steam-catalogo`. O alerta é a
 * LEITURA desses números, feita num lugar só, com o limiar explícito.
 *
 * A regra de peso visual é a que o briefing pediu: sem problema, este painel
 * é uma linha discreta; com problema, ele é a primeira coisa que se vê.
 */

import { useTranslation } from "react-i18next";

import type { SaudeCatalogoSteam, SaudeServicos, SaudeSistema } from "@models/api/tipos";
import { Icone } from "@views/componentes/base";
import { nivelDoPercentual } from "./CartaoRecurso";

export interface Alerta {
  chave: string;
  texto: string;
  nivel: "critico" | "atencao";
}

/**
 * Monta a lista de alertas a partir do que já foi carregado.
 *
 * Recebe os dados em vez de consultar de novo: são exatamente as mesmas
 * respostas que os outros painéis usam, então uma consulta a mais aqui seria
 * carga sem informação nova.
 */
export function montarAlertas(
  sistema: SaudeSistema | undefined,
  servicos: SaudeServicos | undefined,
  steam: SaudeCatalogoSteam | undefined,
  t: (chave: string, opcoes?: Record<string, unknown>) => string,
): Alerta[] {
  const alertas: Alerta[] = [];

  const recursos: Array<[string, number | null | undefined]> = [
    ["cpu", sistema?.cpu?.percentual],
    ["memoria", sistema?.memoria?.percentual],
    ["disco", sistema?.disco?.percentual],
  ];
  for (const [chave, percentual] of recursos) {
    const nivel = nivelDoPercentual(percentual);
    if (nivel === "critico" || nivel === "atencao") {
      alertas.push({
        chave: `recurso-${chave}`,
        nivel: nivel === "critico" ? "critico" : "atencao",
        texto: t(`admin.alertas.recurso.${chave}`, { pct: Math.round(percentual as number) }),
      });
    }
  }

  // Fonte parada é alerta; fonte "sem cadência" (aposentada, como o hltv)
  // nunca é — não há o que esperar dela, e alarmar sobre isso treinaria
  // quem opera a ignorar este painel.
  if (servicos && servicos.fontes_paradas > 0) {
    alertas.push({
      chave: "fontes-paradas",
      nivel: servicos.fontes_paradas >= 3 ? "critico" : "atencao",
      texto: t("admin.alertas.fontesParadas", {
        n: servicos.fontes_paradas,
        total: servicos.fontes_total,
      }),
    });
  }

  if (servicos && servicos.banco_latencia_ms === null) {
    alertas.push({
      chave: "banco-sem-resposta",
      nivel: "critico",
      texto: t("admin.alertas.bancoSemResposta"),
    });
  }

  for (const fase of steam?.fases ?? []) {
    if (fase.registros_falhos > 0) {
      alertas.push({
        chave: `sync-${fase.fase}`,
        nivel: "atencao",
        texto: t("admin.alertas.syncComFalhas", {
          fase: fase.fase,
          n: fase.registros_falhos,
        }),
      });
    }
  }

  return alertas;
}

export function PainelAlertas({ alertas }: { alertas: Alerta[] }) {
  const { t } = useTranslation();

  if (alertas.length === 0) {
    return (
      <section className="flex items-center gap-space-sm rounded-xl bg-surface-container-low/90 p-space-base shadow-2xl">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-tertiary-container/15">
          <Icone nome="check_circle" className="text-[18px] text-tertiary" />
        </span>
        <div className="min-w-0">
          <p className="font-title-code text-title-code text-on-surface">
            {t("admin.alertas.semAlerta")}
          </p>
          <p className="font-body-md text-body-sm text-outline">
            {t("admin.alertas.semAlertaDetalhe")}
          </p>
        </div>
      </section>
    );
  }

  const critico = alertas.some((a) => a.nivel === "critico");

  return (
    <section
      className={`space-y-space-sm rounded-xl p-space-base shadow-2xl ${
        critico ? "bg-error-container/25" : "bg-secondary-container/25"
      }`}
    >
      <h2
        className={`flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest ${
          critico ? "text-error" : "text-secondary"
        }`}
      >
        <Icone nome="warning" className="text-[15px]" />
        {t("admin.alertas.titulo", { n: alertas.length })}
      </h2>

      <ul className="space-y-space-xs">
        {alertas.map((alerta) => (
          <li
            key={alerta.chave}
            className="flex items-start gap-space-xs rounded-lg bg-surface-container-lowest/60 px-space-sm py-space-xs"
          >
            <Icone
              nome={alerta.nivel === "critico" ? "error" : "warning"}
              className={`mt-[2px] shrink-0 text-[15px] ${
                alerta.nivel === "critico" ? "text-error" : "text-secondary"
              }`}
            />
            <span className="font-body-md text-body-sm text-on-surface">{alerta.texto}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
