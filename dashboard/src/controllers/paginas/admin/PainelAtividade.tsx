/**
 * Atividade do sistema — eventos reais, derivados.
 *
 * Não existe tabela de log neste projeto. Em vez de inventar um fluxo de
 * eventos, o backend deriva este feed do que já está gravado com carimbo de
 * tempo próprio: a última coleta de cada fonte (`raw_data`), contas criadas
 * (`dim_usuario`) e as fases de sincronização da Steam. Tudo que aparece
 * aqui aconteceu de fato.
 *
 * A limitação honesta, dita no rodapé: é o ÚLTIMO evento de cada tipo, não
 * um histórico contínuo — para isso seria preciso passar a gravar log, que é
 * outra decisão.
 */

import { useTranslation } from "react-i18next";

import type { EventoAtividade, ListaAtividade } from "@models/api/tipos";
import { Icone } from "@views/componentes/base";
import { Painel } from "@views/componentes/hud";
import { fmtRelativo } from "@util/formatos";

const ICONES: Record<string, string> = {
  coleta: "cloud_download",
  conta: "person_add",
  sincronizacao: "sync",
};

const CORES: Record<string, string> = {
  ok: "text-tertiary",
  atencao: "text-secondary",
  erro: "text-error",
};

const FUNDOS: Record<string, string> = {
  ok: "bg-tertiary-container/15",
  atencao: "bg-secondary-container/25",
  erro: "bg-error-container/25",
};

export function PainelAtividade({ dados }: { dados: ListaAtividade }) {
  const { t } = useTranslation();

  if (dados.eventos.length === 0) {
    return (
      <Painel icone="history" titulo={t("admin.atividade.titulo")}>
        <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-sm text-outline">
          {t("admin.atividade.vazio")}
        </p>
      </Painel>
    );
  }

  return (
    <Painel
      icone="history"
      titulo={t("admin.atividade.titulo")}
      descricao={t("admin.atividade.descricao")}
    >
      <ul className="space-y-space-xxs">
        {dados.eventos.map((evento: EventoAtividade, indice) => (
          <li
            key={`${evento.tipo}-${evento.titulo}-${indice}`}
            className="flex items-center gap-space-sm rounded-lg px-space-sm py-space-xs transition-colors hover:bg-surface-container"
          >
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
                FUNDOS[evento.nivel] ?? FUNDOS.ok
              }`}
            >
              <Icone
                nome={ICONES[evento.tipo] ?? "bolt"}
                className={`text-[13px] ${CORES[evento.nivel] ?? CORES.ok}`}
              />
            </span>

            <span className="min-w-0 flex-1">
              <span className="block truncate font-body-md text-body-sm text-on-surface">
                {evento.titulo}
              </span>
              {evento.detalhe && (
                <span className="block truncate font-body-md text-[11px] leading-tight text-outline">
                  {evento.detalhe}
                </span>
              )}
            </span>

            <span className="shrink-0 font-title-code text-[11px] tabular-nums text-outline">
              {fmtRelativo(evento.quando)}
            </span>
          </li>
        ))}
      </ul>

      <p className="font-body-md text-[11px] leading-tight text-outline">
        {t("admin.atividade.rodape")}
      </p>
    </Painel>
  );
}
