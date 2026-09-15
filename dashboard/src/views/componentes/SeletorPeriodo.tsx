/**
 * Recorte de tempo das séries do catálogo (7 / 30 / 90 dias / 1 ano).
 *
 * A regra que justifica o componente existir em vez de quatro pílulas soltas:
 * **um período maior do que o histórico coletado fica desabilitado**, com o
 * motivo no `title`. Oferecer "1 ano" sobre duas semanas de coleta devolveria
 * exatamente a mesma curva de "30 dias" e daria a entender que existe um ano
 * de dado — o mesmo cuidado que a ordenação "trending" já toma quando ainda
 * não há uma segunda coleta para comparar.
 */

import { useTranslation } from "react-i18next";

export const PERIODOS = [7, 30, 90, 365] as const;
export type Periodo = (typeof PERIODOS)[number];

export function SeletorPeriodo({
  valor,
  aoMudar,
  diasDisponiveis,
}: {
  valor: Periodo;
  aoMudar: (periodo: Periodo) => void;
  /** Dias de histórico que existem de fato. `null` enquanto carrega. */
  diasDisponiveis: number | null;
}) {
  const { t } = useTranslation();

  return (
    <div
      role="group"
      aria-label={t("catalogoLayout.periodo.rotulo")}
      className="flex items-center gap-space-xxs rounded-full bg-surface-container-lowest/80 p-space-xxs ring-1 ring-outline-variant/30"
    >
      {PERIODOS.map((periodo) => {
        // Tolerância de um dia: com 13,4 dias coletados, "7 dias" é honesto e
        // "30" não — mas não faz sentido bloquear "7" por causa de arredondamento.
        const indisponivel =
          diasDisponiveis !== null && periodo > Math.ceil(diasDisponiveis);
        const ativo = valor === periodo;

        return (
          <button
            key={periodo}
            type="button"
            disabled={indisponivel}
            aria-pressed={ativo}
            title={
              indisponivel
                ? t("catalogoLayout.periodo.indisponivel", {
                    dias: Math.floor(diasDisponiveis ?? 0),
                  })
                : undefined
            }
            onClick={() => aoMudar(periodo)}
            className={`rounded-full px-space-sm py-space-xxs font-title-code text-title-code transition-colors ${
              ativo
                ? "bg-primary-container text-on-primary"
                : indisponivel
                  ? "cursor-not-allowed text-outline/50"
                  : "text-on-surface-variant hover:bg-surface-container-high/60 hover:text-on-surface"
            }`}
          >
            {periodo === 365
              ? t("catalogoLayout.periodo.umAno")
              : t("catalogoLayout.periodo.dias", { dias: periodo })}
          </button>
        );
      })}
    </div>
  );
}
