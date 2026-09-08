/**
 * O topo da home: o confronto em destaque (com velocímetro do modelo) e a
 * grade "Acontecendo agora" de todos os jogos.
 *
 * Lê `/api/home/destaques` sozinho. Se não há nada por vir em jogo nenhum, a
 * seção não renderiza — a home segue com os KPIs abaixo.
 */

import { Link } from "react-router-dom";

import { useDestaquesHome } from "../api/consultas";
import type { ConfrontoAoVivo, DestaqueConfronto } from "../api/tipos";
import { corDoJogo, TOKENS } from "../tema";
import { fmtDataHora, fmtRelativo } from "../utilitarios/formatos";
import { Icone, Selo } from "./base";
import { Velocimetro } from "./Velocimetro";

/** Escudo pequeno — logo quando há, senão as iniciais. */
function Escudo({
  logo,
  tag,
  nome,
  tamanho = 24,
}: {
  logo: string | null;
  tag: string | null;
  nome: string;
  tamanho?: number;
}) {
  const estilo = { width: tamanho, height: tamanho };
  if (logo) {
    return (
      <span
        className="flex shrink-0 items-center justify-center rounded bg-neutral-200 p-[2px]"
        style={estilo}
      >
        <img src={logo} alt="" className="max-h-full max-w-full object-contain" />
      </span>
    );
  }
  return (
    <span
      className="flex shrink-0 items-center justify-center rounded bg-surface-container-highest text-[9px] font-bold uppercase leading-none text-outline"
      style={estilo}
      aria-hidden
    >
      {(tag || nome).slice(0, 3)}
    </span>
  );
}

function EtiquetaJogo({ jogo, nome }: { jogo: string; nome: string }) {
  return (
    <span className="flex items-center gap-space-xxs font-label-caps text-label-caps uppercase tracking-wider text-outline">
      <span
        className="h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ background: corDoJogo(jogo) }}
        aria-hidden
      />
      {nome}
    </span>
  );
}

function CartaoAoVivo({ c }: { c: ConfrontoAoVivo }) {
  return (
    <div
      className="flex flex-col gap-space-xs overflow-hidden rounded-lg border border-outline-variant/25 bg-surface-container-lowest"
      style={{ borderLeft: `3px solid ${corDoJogo(c.jogo)}` }}
    >
      <div className="flex items-center justify-between gap-space-xs px-space-sm pt-space-xs">
        <EtiquetaJogo jogo={c.jogo} nome={c.jogo_nome} />
        {c.ao_vivo ? (
          <span className="flex items-center gap-space-xxs font-badge-status text-badge-status uppercase tracking-widest text-error">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-error" aria-hidden />
            ao vivo
          </span>
        ) : (
          <span
            className="font-badge-status text-badge-status tabular-nums text-outline"
            title={fmtDataHora(c.inicio_previsto)}
          >
            {fmtRelativo(c.inicio_previsto)}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-space-xxs px-space-sm">
        <div className="flex items-center gap-space-xs">
          <Escudo logo={c.equipe_a_logo} tag={c.equipe_a_tag} nome={c.equipe_a_nome} />
          <span className="min-w-0 flex-1 truncate font-title-code text-title-code text-on-surface">
            {c.equipe_a_nome}
          </span>
        </div>
        <div className="flex items-center gap-space-xs">
          <Escudo logo={c.equipe_b_logo} tag={c.equipe_b_tag} nome={c.equipe_b_nome} />
          <span className="min-w-0 flex-1 truncate font-title-code text-title-code text-on-surface">
            {c.equipe_b_nome}
          </span>
        </div>
      </div>

      <div className="truncate px-space-sm pb-space-xs font-body-sm text-body-sm text-outline">
        {c.torneio ?? "—"}
      </div>
    </div>
  );
}

function Destaque({ c }: { c: DestaqueConfronto }) {
  const favoritoA = c.probabilidade_a >= 0.5;
  const pctA = Math.round(c.probabilidade_a * 100);

  return (
    <div className="flex flex-col gap-space-md rounded-xl border border-outline-variant/25 bg-surface-container-low/90 p-space-base shadow-2xl">
      <div className="flex items-center justify-between gap-space-sm">
        <h2 className="flex items-center gap-space-xs font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
          <span style={{ color: TOKENS.modelo }}>
            <Icone nome="speed" className="text-[20px]" />
          </span>
          Destaque do dia
        </h2>
        <span
          className="inline-flex items-center gap-space-xxs rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase tracking-wider"
          style={{ color: TOKENS.modelo, background: `${TOKENS.modelo}14` }}
        >
          <Icone nome="bolt" className="text-[13px]" />
          previsão
        </span>
      </div>

      <EtiquetaJogo jogo={c.jogo} nome={`${c.jogo_nome} · ${c.torneio ?? "—"}`} />

      <div className="flex justify-center py-space-xs">
        <Velocimetro
          probabilidade={c.probabilidade_a}
          rotulo={(c.equipe_a_tag || c.equipe_a_nome).slice(0, 16)}
          tamanho={200}
        />
      </div>

      <div className="flex flex-col gap-space-xxs">
        <div
          className="flex items-center gap-space-xs rounded px-space-xs py-space-xxs"
          style={{ background: favoritoA ? `${TOKENS.modelo}12` : undefined }}
        >
          <Escudo logo={c.equipe_a_logo} tag={c.equipe_a_tag} nome={c.equipe_a_nome} tamanho={26} />
          <span
            className={`min-w-0 flex-1 truncate font-title-code text-title-code ${
              favoritoA ? "font-bold text-on-surface" : "text-on-surface-variant"
            }`}
          >
            {c.equipe_a_nome}
          </span>
          <span className="shrink-0 font-headline-sm text-headline-sm tabular-nums text-on-surface">
            {pctA}%
          </span>
        </div>
        <div
          className="flex items-center gap-space-xs rounded px-space-xs py-space-xxs"
          style={{ background: !favoritoA ? `${TOKENS.modelo}12` : undefined }}
        >
          <Escudo logo={c.equipe_b_logo} tag={c.equipe_b_tag} nome={c.equipe_b_nome} tamanho={26} />
          <span
            className={`min-w-0 flex-1 truncate font-title-code text-title-code ${
              !favoritoA ? "font-bold text-on-surface" : "text-on-surface-variant"
            }`}
          >
            {c.equipe_b_nome}
          </span>
          <span className="shrink-0 font-headline-sm text-headline-sm tabular-nums text-on-surface">
            {100 - pctA}%
          </span>
        </div>
      </div>

      <div className="flex items-center justify-between gap-space-sm border-t border-outline-variant/20 pt-space-sm font-badge-status text-badge-status uppercase tracking-wider text-outline">
        <span className="flex items-center gap-space-xs">
          {c.formato && (
            <span className="rounded bg-surface-container px-space-xxs py-[1px] text-on-surface-variant">
              {c.formato}
            </span>
          )}
          <span className="tabular-nums" title={fmtDataHora(c.inicio_previsto)}>
            {fmtRelativo(c.inicio_previsto)}
          </span>
        </span>
        <Link
          to={`/esports/${c.jogo}/previsao`}
          className="inline-flex items-center gap-space-xxs text-primary hover:text-primary-fixed"
        >
          abrir análise <Icone nome="arrow_forward" className="text-[14px]" />
        </Link>
      </div>
    </div>
  );
}

export function AcontecendoAgora() {
  const { data } = useDestaquesHome();

  if (!data || (data.ao_vivo.length === 0 && !data.destaque)) return null;

  return (
    <section className="grid grid-cols-1 gap-space-base xl:grid-cols-[minmax(0,22rem)_1fr]">
      {data.destaque ? (
        <Destaque c={data.destaque} />
      ) : (
        <div />
      )}

      <div className="flex flex-col gap-space-sm">
        <div className="flex items-center justify-between gap-space-sm">
          <h2 className="flex items-center gap-space-xs font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
            <Icone nome="sensors" className="text-[20px] text-primary" />
            Acontecendo agora
          </h2>
          <Selo cor="primario">{data.ao_vivo.length} confrontos</Selo>
        </div>
        <div className="grid grid-cols-1 gap-space-sm sm:grid-cols-2">
          {data.ao_vivo.map((c) => (
            <CartaoAoVivo key={`${c.jogo}:${c.id_externo}`} c={c} />
          ))}
        </div>
      </div>
    </section>
  );
}
