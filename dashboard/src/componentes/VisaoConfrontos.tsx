/**
 * Uma lista de confrontos em três formas — o leitor escolhe e a escolha fica.
 * Serve tanto os DECIDIDOS (aba Resultados, com placar) quanto os POR VIR
 * (aba Partidas, sem placar, horário no lugar).
 *
 * - **Cartões** (padrão): grade de scorecards, um por confronto. É o que lê
 *   melhor de relance e o que funciona no celular.
 * - **Por torneio**: uma seção por campeonato, empilhadas de cima para baixo,
 *   os cartões em grade dentro de cada uma. Para ver um campeonato de uma vez.
 * - **Lista**: a linha densa, o placar/horário alinhado. Para varrer rápido.
 *
 * O modal de detalhe por mapa (`ModalConfrontoDetalhe`) mora aqui, então os
 * três modos abrem o mesmo detalhe sem duplicar estado.
 */

import { useEffect, useMemo, useState } from "react";

import type { ConfrontoResultado, Partida, PartidaAgendada } from "../api/tipos";
import { PALETA_POLOS } from "../tema";
import { fmtDataHora, fmtRelativo } from "../utilitarios/formatos";
import { CartaoConfronto, paraCartao, type DadosConfronto } from "./CartaoConfronto";
import { ModalConfrontoDetalhe } from "./ModalConfrontoDetalhe";
import { Icone } from "./base";

type Modo = "cartoes" | "kanban" | "lista";

/** O que a `VisaoConfrontos` aceita: confronto decidido, partida por vir ou
 *  partida de Dota (grão de jogo). O `coercao` diz como virar `DadosConfronto`. */
type Entrada = ConfrontoResultado | PartidaAgendada | Partida;

const MODOS: { id: Modo; icone: string; rotulo: string }[] = [
  { id: "cartoes", icone: "grid_view", rotulo: "Cartões" },
  { id: "kanban", icone: "workspaces", rotulo: "Por torneio" },
  { id: "lista", icone: "view_agenda", rotulo: "Lista" },
];

/** Chave padrão do localStorage — a aba Partidas passa uma própria. */
export const CHAVE_MODO_PADRAO = "playdb:confrontos-modo";

function ehModo(v: unknown): v is Modo {
  return v === "cartoes" || v === "kanban" || v === "lista";
}

function lerModo(chave: string): Modo {
  try {
    const v = localStorage.getItem(chave);
    if (ehModo(v)) return v;
  } catch {
    /* localStorage indisponível: usa o padrão */
  }
  return "cartoes";
}

/** Alterna Cartões / Por torneio / Lista. */
export function SeletorModoConfrontos({
  modo,
  aoMudar,
}: {
  modo: Modo;
  aoMudar: (m: Modo) => void;
}) {
  return (
    <div className="flex items-center rounded bg-surface-container-low p-space-xxs shadow-sm">
      {MODOS.map((m) => (
        <button
          key={m.id}
          type="button"
          aria-pressed={modo === m.id}
          title={m.rotulo}
          onClick={() => aoMudar(m.id)}
          className={`flex h-8 items-center gap-space-xxs rounded px-space-sm font-title-code text-title-code transition-colors ${
            modo === m.id
              ? "bg-surface-container-high text-primary shadow-sm"
              : "text-on-surface-variant hover:text-on-surface"
          }`}
        >
          <Icone nome={m.icone} className="text-[16px]" />
          <span className="hidden sm:inline">{m.rotulo}</span>
        </button>
      ))}
    </div>
  );
}

export function useModoConfrontos(chave: string = CHAVE_MODO_PADRAO) {
  const [modo, setModo] = useState<Modo>(() => lerModo(chave));
  useEffect(() => {
    try {
      localStorage.setItem(chave, modo);
    } catch {
      /* ok */
    }
  }, [chave, modo]);
  return [modo, setModo] as const;
}

/* ----------------------------- Lista densa ----------------------------- */

function Placar({
  valor,
  venceu,
  semResultado,
}: {
  valor: number | null | undefined;
  venceu: boolean;
  semResultado: boolean;
}) {
  const cor = semResultado
    ? undefined
    : venceu
      ? PALETA_POLOS.positivo
      : PALETA_POLOS.negativo;
  return (
    <span
      className="w-[1.1rem] text-center font-headline-sm text-headline-sm tabular-nums"
      style={{ color: cor }}
    >
      {valor ?? "–"}
    </span>
  );
}

function Sigla({
  logo,
  tag,
  nome,
}: {
  logo?: string | null;
  tag: string | null | undefined;
  nome: string;
}) {
  if (logo) {
    return (
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm bg-neutral-200 p-[2px]">
        <img src={logo} alt="" className="max-h-full max-w-full object-contain" />
      </span>
    );
  }
  return (
    <span
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm bg-surface-container-highest text-[9px] font-bold uppercase leading-none text-outline"
      aria-hidden
    >
      {(tag || nome).slice(0, 2)}
    </span>
  );
}

function LinhaLista({
  c,
  aoClicar,
  par,
}: {
  c: DadosConfronto;
  aoClicar?: () => void;
  par: boolean;
}) {
  const semResultado = c.vitoria_a == null && c.placar_a == null;
  // Dota: decidido mas sem placar numérico (BO1) — o vencedor destaca no nome.
  const semPlacar = c.placar_a == null && c.placar_b == null;
  const nomeA = `truncate font-title-code text-title-code ${
    c.vitoria_a === true ? "font-bold text-on-surface" : "text-on-surface-variant"
  }`;
  const nomeB = `truncate font-title-code text-title-code ${
    c.vitoria_a === false ? "font-bold text-on-surface" : "text-on-surface-variant"
  }`;

  return (
    <li
      onClick={aoClicar}
      className={[
        "flex flex-col gap-space-xxs px-space-sm py-space-xs sm:flex-row sm:items-center sm:gap-space-md",
        par ? "bg-white/[0.015]" : "",
        aoClicar
          ? "cursor-pointer transition-colors hover:bg-surface-container-high/50"
          : "",
      ].join(" ")}
    >
      <div className="flex shrink-0 items-center gap-space-xs sm:w-[23rem] lg:w-[28rem]">
        <span className={`min-w-0 flex-1 text-right ${nomeA}`} title={c.equipe_a_nome}>
          {c.equipe_a_nome}
        </span>
        <Sigla logo={c.equipe_a_logo} tag={c.equipe_a_tag} nome={c.equipe_a_nome} />
        {semPlacar && !semResultado ? (
          <span className="shrink-0 px-0.5 font-label-caps text-label-caps uppercase tracking-wider text-outline">
            vs
          </span>
        ) : (
          <span className="flex shrink-0 items-center gap-0.5">
            <Placar valor={c.placar_a} venceu={c.vitoria_a === true} semResultado={semResultado} />
            <span className="text-outline">-</span>
            <Placar valor={c.placar_b} venceu={c.vitoria_a === false} semResultado={semResultado} />
          </span>
        )}
        <Sigla logo={c.equipe_b_logo} tag={c.equipe_b_tag} nome={c.equipe_b_nome} />
        <span className={`min-w-0 flex-1 text-left ${nomeB}`} title={c.equipe_b_nome}>
          {c.equipe_b_nome}
        </span>
      </div>

      <div className="flex min-w-0 flex-1 items-center gap-space-xs font-body-sm text-body-sm text-outline">
        <Icone nome="emoji_events" className="hidden shrink-0 text-[14px] sm:inline" />
        <span className="truncate" title={c.torneio ?? undefined}>
          {c.torneio ?? "—"}
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-space-sm font-badge-status text-badge-status uppercase tracking-wider text-outline">
        {c.tem_detalhe && (
          <Icone nome="scoreboard" className="shrink-0 text-[14px] text-primary" />
        )}
        {c.nota && (
          <span className="hidden tabular-nums text-on-surface-variant sm:inline">
            {c.nota}
          </span>
        )}
        {c.formato && (
          <span className="rounded bg-surface-container px-space-xxs py-[1px] text-on-surface-variant">
            {c.formato}
          </span>
        )}
        <span className="tabular-nums">
          {semResultado ? fmtDataHora(c.inicio_previsto) : fmtRelativo(c.inicio_previsto)}
        </span>
      </div>
    </li>
  );
}

/* --------------------------------- Visão --------------------------------- */

export function VisaoConfrontos<T extends Entrada = ConfrontoResultado | PartidaAgendada>({
  confrontos,
  modo,
  coercao = paraCartao,
  aoClicarItem,
}: {
  confrontos: T[];
  modo: Modo;
  /** Como virar cada entrada em `DadosConfronto`. Padrão: confronto/agenda. */
  coercao?: (entrada: T) => DadosConfronto;
  /** Clique num cartão/linha. Quando definido, substitui o modal de detalhe. */
  aoClicarItem?: (c: DadosConfronto) => void;
}) {
  const [aberto, setAberto] = useState<string | null>(null);

  const itens = useMemo<DadosConfronto[]>(
    () => confrontos.map((entrada) => coercao(entrada)),
    [confrontos, coercao],
  );

  const abrir = (c: DadosConfronto) => {
    if (aoClicarItem) return () => aoClicarItem(c);
    return c.tem_detalhe ? () => setAberto(c.id_externo) : undefined;
  };

  const porTorneio = useMemo(() => {
    const mapa = new Map<string, DadosConfronto[]>();
    for (const c of itens) {
      const chave = c.torneio ?? "Sem torneio";
      mapa.set(chave, [...(mapa.get(chave) ?? []), c]);
    }
    // Coluna com mais confrontos primeiro: é onde o olho começa.
    return [...mapa.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [itens]);

  return (
    <>
      {modo === "cartoes" && (
        <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2 xl:grid-cols-3">
          {itens.map((c) => (
            <CartaoConfronto key={c.id_externo} confronto={c} aoClicar={abrir(c)} />
          ))}
        </div>
      )}

      {modo === "kanban" && (
        <div className="flex flex-col gap-space-lg">
          {porTorneio.map(([torneio, lista]) => (
            <section key={torneio} className="flex flex-col gap-space-sm">
              <div className="flex items-center gap-space-sm border-b border-outline-variant/20 pb-space-xs">
                <Icone
                  nome="emoji_events"
                  className="shrink-0 text-[16px] text-outline"
                />
                <span
                  className="min-w-0 truncate font-title-code text-title-code uppercase tracking-wider text-on-surface"
                  title={torneio}
                >
                  {torneio}
                </span>
                <span className="shrink-0 rounded bg-surface-container px-space-xs font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  {lista.length}
                </span>
              </div>
              <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2 xl:grid-cols-3">
                {lista.map((c) => (
                  <CartaoConfronto
                    key={c.id_externo}
                    confronto={c}
                    semCabecalho
                    aoClicar={abrir(c)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {modo === "lista" && (
        <ul className="divide-y divide-outline-variant/10 overflow-hidden rounded-lg bg-surface-container-lowest">
          {itens.map((c, i) => (
            <LinhaLista key={c.id_externo} c={c} aoClicar={abrir(c)} par={i % 2 === 1} />
          ))}
        </ul>
      )}

      <ModalConfrontoDetalhe idExterno={aberto} aoFechar={() => setAberto(null)} />
    </>
  );
}
