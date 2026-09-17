/**
 * Card de um recurso do servidor (CPU, memória, disco, uptime).
 *
 * Denso de propósito: percentual grande, barra, valor usado/total e status
 * numa altura só. É o primeiro bloco do painel e responde "o servidor está
 * bem?" sem precisar ler nada.
 *
 * **Sobre o mini-gráfico.** O backend devolve só o valor ATUAL de cada
 * recurso — não existe histórico de CPU gravado em lugar nenhum. Em vez de
 * desenhar uma silhueta decorativa, a série aqui é acumulada no navegador a
 * partir das leituras reais que chegam a cada 10s (`useSerieObservada`), e o
 * rodapé diz exatamente isso: é o que foi observado desde que a tela abriu,
 * não histórico do servidor. Com menos de dois pontos, não há gráfico.
 */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Icone } from "@views/componentes/base";
import { BarraFina, Sparkline } from "@views/componentes/hud";

/** Faixas de status. Acima de 90% é crítico em qualquer recurso; acima de 75%
 * merece atenção. São limiares de operação, não estética — a cor muda porque
 * o número mudou de significado. */
const LIMITE_ATENCAO = 75;
const LIMITE_CRITICO = 90;

export type NivelRecurso = "ok" | "atencao" | "critico" | "sem_dado";

export function nivelDoPercentual(percentual: number | null | undefined): NivelRecurso {
  if (percentual === null || percentual === undefined) return "sem_dado";
  if (percentual >= LIMITE_CRITICO) return "critico";
  if (percentual >= LIMITE_ATENCAO) return "atencao";
  return "ok";
}

const CORES: Record<NivelRecurso, { texto: string; barra: string; ponto: string }> = {
  ok: { texto: "text-tertiary", barra: "bg-tertiary-container", ponto: "bg-tertiary-container" },
  atencao: { texto: "text-secondary", barra: "bg-secondary-fixed-dim", ponto: "bg-secondary-fixed-dim" },
  critico: { texto: "text-error", barra: "bg-error", ponto: "bg-error" },
  sem_dado: { texto: "text-outline", barra: "bg-outline/40", ponto: "bg-outline" },
};

/**
 * Guarda as leituras que já chegaram, para desenhar o mini-gráfico.
 *
 * Não é cache de dado do servidor: é a memória da própria sessão de quem
 * está olhando. Some ao recarregar a página, e é por isso que o rodapé do
 * card diz "desde que abriu" em vez de prometer histórico.
 */
export function useSerieObservada(valor: number | null | undefined, maximo = 30): number[] {
  const [serie, setSerie] = useState<number[]>([]);
  // `valor` entra no ref pra que o efeito dependa só do valor em si — sem
  // isto, um re-render com o mesmo número duplicaria o ponto.
  const ultimo = useRef<number | null>(null);

  useEffect(() => {
    if (valor === null || valor === undefined) return;
    if (ultimo.current === valor) return;
    ultimo.current = valor;
    setSerie((anterior) => [...anterior, valor].slice(-maximo));
  }, [valor, maximo]);

  return serie;
}

export function CartaoRecurso({
  rotulo,
  icone,
  percentual,
  detalhe,
  atualizando = false,
}: {
  rotulo: string;
  icone: string;
  /** `null` quando a fonte não soube informar — o card mostra "sem dado". */
  percentual: number | null;
  detalhe: string | null;
  atualizando?: boolean;
}) {
  const { t } = useTranslation();
  const nivel = nivelDoPercentual(percentual);
  const cor = CORES[nivel];
  const serie = useSerieObservada(percentual);

  return (
    <article className="flex flex-col gap-space-sm rounded-xl bg-surface-container-low/90 p-space-base shadow-2xl">
      <header className="flex items-center justify-between gap-space-sm">
        <span className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-on-surface-variant">
          <Icone nome={icone} className="text-[15px] text-primary" />
          {rotulo}
        </span>
        <span
          className={`inline-flex shrink-0 items-center gap-space-xxs rounded bg-surface-container-high px-space-xs py-space-xxs font-badge-status text-badge-status uppercase ${cor.texto}`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${cor.ponto} ${atualizando ? "animate-pulse" : ""}`}
            aria-hidden
          />
          {t(`admin.recurso.nivel.${nivel}`)}
        </span>
      </header>

      <div className="flex items-end justify-between gap-space-sm">
        <span
          className={`font-headline-lg text-headline-lg tabular-nums ${
            nivel === "sem_dado" ? "text-outline" : "text-on-surface"
          }`}
        >
          {percentual === null ? "—" : `${percentual.toFixed(0)}%`}
        </span>
        {serie.length > 1 && (
          <span className="min-w-0 flex-1 pb-space-xxs" aria-hidden>
            <Sparkline valores={serie} className={cor.texto} compacto />
          </span>
        )}
      </div>

      <BarraFina largura={percentual ?? 0} className={cor.barra} />

      <p className="font-body-md text-body-sm text-on-surface-variant">
        {detalhe ?? t("admin.recurso.semDado")}
      </p>

      {serie.length > 1 && (
        <p className="font-body-md text-[11px] leading-tight text-outline">
          {t("admin.recurso.serieObservada", { n: serie.length })}
        </p>
      )}
    </article>
  );
}

/**
 * Card de uptime — sem percentual, porque não existe "percentual de uptime"
 * aqui: o backend informa há quanto tempo a máquina está de pé, e nada mais.
 * Inventar uma barra de 0-100 para isso seria decoração.
 */
export function CartaoUptime({
  segundos,
  fonte,
}: {
  segundos: number | null;
  /** "netdata" = uptime do host (VPS); "local" = do container. Muda o que o
   * número significa, então a tela diz qual é. */
  fonte: string;
}) {
  const { t } = useTranslation();

  const texto = (() => {
    if (segundos === null) return null;
    const dias = Math.floor(segundos / 86400);
    const horas = Math.floor((segundos % 86400) / 3600);
    const minutos = Math.floor((segundos % 3600) / 60);
    if (dias > 0) return `${dias}d ${String(horas).padStart(2, "0")}h`;
    if (horas > 0) return `${horas}h ${String(minutos).padStart(2, "0")}m`;
    return `${minutos}m`;
  })();

  return (
    <article className="flex flex-col gap-space-sm rounded-xl bg-surface-container-low/90 p-space-base shadow-2xl">
      <header className="flex items-center justify-between gap-space-sm">
        <span className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-on-surface-variant">
          <Icone nome="schedule" className="text-[15px] text-primary" />
          {t("admin.recurso.uptime")}
        </span>
        <span
          className={`inline-flex shrink-0 items-center gap-space-xxs rounded bg-surface-container-high px-space-xs py-space-xxs font-badge-status text-badge-status uppercase ${
            texto ? "text-tertiary" : "text-outline"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${texto ? "bg-tertiary-container" : "bg-outline"}`}
            aria-hidden
          />
          {texto ? t("admin.recurso.nivel.ok") : t("admin.recurso.nivel.sem_dado")}
        </span>
      </header>

      <span
        className={`font-headline-lg text-headline-lg tabular-nums ${
          texto ? "text-on-surface" : "text-outline"
        }`}
      >
        {texto ?? "—"}
      </span>

      <p className="font-body-md text-body-sm text-on-surface-variant">
        {texto
          ? t(fonte === "netdata" ? "admin.recurso.uptimeHost" : "admin.recurso.uptimeContainer")
          : t("admin.recurso.semDado")}
      </p>
    </article>
  );
}
