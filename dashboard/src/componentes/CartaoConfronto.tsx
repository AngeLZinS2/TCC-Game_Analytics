/**
 * Um confronto como cartão — o placar da série no formato de scorecard de
 * esports: cabeçalho com o torneio, os dois times empilhados (o vencedor com
 * barra de acento e o placar em verde, o perdedor apagado) e um rodapé com o
 * formato e quando foi.
 *
 * Serve tanto o resultado (com placar) quanto a partida por vir (sem placar,
 * horário no rodapé). O `semCabecalho` some com a faixa do torneio quando o
 * cartão já vive dentro de uma coluna de torneio (visão kanban).
 */

import type { ReactNode } from "react";

import type { ConfrontoResultado, PartidaAgendada } from "../api/tipos";
import { PALETA_POLOS } from "../tema";
import { fmtDataHora, fmtRelativo } from "../utilitarios/formatos";
import { Icone } from "./base";

/** O mínimo que o cartão precisa — o resto é opcional e cai no "por vir". */
export interface DadosConfronto {
  id_externo: string;
  equipe_a_nome: string;
  equipe_b_nome: string;
  equipe_a_logo?: string | null;
  equipe_b_logo?: string | null;
  equipe_a_tag?: string | null;
  equipe_b_tag?: string | null;
  placar_a?: number | null;
  placar_b?: number | null;
  vitoria_a?: boolean | null;
  torneio: string | null;
  formato: string | null;
  inicio_previsto: string;
  tem_detalhe?: boolean;
}

export function paraCartao(
  c: ConfrontoResultado | PartidaAgendada,
): DadosConfronto {
  return { ...c } as DadosConfronto;
}

function Escudo({
  logo,
  tag,
  nome,
}: {
  logo: string | null | undefined;
  tag: string | null | undefined;
  nome: string;
}) {
  if (logo) {
    return (
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-neutral-200 p-[3px]">
        {/* Sem `loading="lazy"`: são ~40-70 PNGs de poucos KB e o lazy às
            vezes não dispara dentro do painel (fica plaquinha em branco). */}
        <img
          src={logo}
          alt=""
          className="max-h-full max-w-full object-contain"
        />
      </span>
    );
  }
  return (
    <span
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-surface-container-highest text-[10px] font-bold uppercase leading-none text-outline"
      aria-hidden
    >
      {(tag || nome).slice(0, 2)}
    </span>
  );
}

function LinhaTime({
  nome,
  logo,
  tag,
  placar,
  venceu,
  perdeu,
  agendada,
}: {
  nome: string;
  logo: string | null | undefined;
  tag: string | null | undefined;
  placar: number | null | undefined;
  venceu: boolean;
  perdeu: boolean;
  agendada: boolean;
}) {
  return (
    <div
      className="flex items-center gap-space-sm px-space-sm py-space-xs"
      style={{
        boxShadow: venceu ? `inset 3px 0 0 ${PALETA_POLOS.positivo}` : undefined,
        background: venceu ? `${PALETA_POLOS.positivo}0f` : undefined,
      }}
    >
      <Escudo logo={logo} tag={tag} nome={nome} />
      <span
        className={`min-w-0 flex-1 truncate font-title-code text-title-code ${
          venceu ? "font-bold text-on-surface" : perdeu ? "text-outline" : "text-on-surface-variant"
        }`}
        title={nome}
      >
        {nome}
      </span>
      {!agendada && (
        <span
          className="shrink-0 font-headline-sm text-headline-sm tabular-nums"
          style={{
            color: venceu
              ? PALETA_POLOS.positivo
              : perdeu
                ? PALETA_POLOS.negativo
                : undefined,
          }}
        >
          {placar ?? "–"}
        </span>
      )}
    </div>
  );
}

export function CartaoConfronto({
  confronto: c,
  semCabecalho = false,
  aoClicar,
}: {
  confronto: DadosConfronto;
  semCabecalho?: boolean;
  aoClicar?: () => void;
}) {
  const agendada = c.vitoria_a == null && c.placar_a == null;
  const venceuA = c.vitoria_a === true;
  const venceuB = c.vitoria_a === false;
  const decidido = venceuA || venceuB;
  const clicavel = Boolean(aoClicar);

  const corpo: ReactNode = (
    <>
      {!semCabecalho && (
        <div className="flex items-center gap-space-xs border-b border-outline-variant/20 px-space-sm py-space-xs font-label-caps text-label-caps uppercase tracking-wider text-outline">
          <Icone nome="emoji_events" className="shrink-0 text-[13px]" />
          <span className="truncate" title={c.torneio ?? undefined}>
            {c.torneio ?? "Sem torneio"}
          </span>
        </div>
      )}

      <div className="divide-y divide-outline-variant/10">
        <LinhaTime
          nome={c.equipe_a_nome}
          logo={c.equipe_a_logo}
          tag={c.equipe_a_tag}
          placar={c.placar_a}
          venceu={venceuA}
          perdeu={decidido && !venceuA}
          agendada={agendada}
        />
        <LinhaTime
          nome={c.equipe_b_nome}
          logo={c.equipe_b_logo}
          tag={c.equipe_b_tag}
          placar={c.placar_b}
          venceu={venceuB}
          perdeu={decidido && !venceuB}
          agendada={agendada}
        />
      </div>

      <div className="flex items-center justify-between gap-space-sm border-t border-outline-variant/20 px-space-sm py-space-xs font-badge-status text-badge-status uppercase tracking-wider text-outline">
        <span className="flex items-center gap-space-xs">
          {c.formato && (
            <span className="rounded bg-surface-container px-space-xxs py-[1px] text-on-surface-variant">
              {c.formato}
            </span>
          )}
          <span
            className="tabular-nums"
            title={fmtDataHora(c.inicio_previsto)}
          >
            {agendada ? fmtDataHora(c.inicio_previsto) : fmtRelativo(c.inicio_previsto)}
          </span>
        </span>
        {c.tem_detalhe && (
          <span className="inline-flex shrink-0 items-center gap-space-xxs text-primary">
            <Icone nome="scoreboard" className="text-[13px]" />
            por mapa
          </span>
        )}
      </div>
    </>
  );

  const classe =
    "flex flex-col overflow-hidden rounded-lg border border-outline-variant/25 bg-surface-container-lowest";

  return clicavel ? (
    <button
      type="button"
      onClick={aoClicar}
      className={`${classe} text-left transition-colors hover:border-primary-container/50 hover:bg-surface-container-high/40`}
    >
      {corpo}
    </button>
  ) : (
    <div className={classe}>{corpo}</div>
  );
}
