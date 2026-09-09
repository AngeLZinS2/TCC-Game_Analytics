/**
 * Onde a partida vai passar. Um canal → link direto; vários → um `<details>`
 * que abre a lista (Twitch/YouTube/Kick, idioma quando a fonte informa).
 *
 * `<details>` de propósito: sem estado, sem JS, acessível, e não rouba o clique
 * do card em volta (só o `<summary>` alterna).
 */

import type { StreamCanal } from "../api/tipos";
import { Icone } from "./base";

const ICONE_PLATAFORMA: Record<string, string> = {
  twitch: "videocam",
  youtube: "smart_display",
  kick: "sports_esports",
};

function LinhaCanal({ c }: { c: StreamCanal }) {
  return (
    <a
      href={c.url}
      target="_blank"
      rel="noreferrer"
      className="flex items-center gap-space-xs rounded px-space-xs py-space-xxs font-body-sm text-body-sm text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface"
      onClick={(e) => e.stopPropagation()}
    >
      <Icone
        nome={ICONE_PLATAFORMA[c.plataforma] ?? "public"}
        className="text-[14px] text-primary"
      />
      <span className="min-w-0 flex-1 truncate">{c.nome}</span>
      {c.lingua && (
        <span className="shrink-0 rounded bg-surface-container-highest px-space-xxs font-badge-status text-badge-status text-outline">
          {c.lingua}
        </span>
      )}
      {c.principal && (
        <span className="shrink-0 font-badge-status text-badge-status uppercase text-primary">
          oficial
        </span>
      )}
    </a>
  );
}

export function CanaisTransmissao({
  streams,
  compacto = false,
}: {
  streams: StreamCanal[] | undefined;
  /** No card da grade o espaço é curto: só o gatilho, a lista abre por cima. */
  compacto?: boolean;
}) {
  if (!streams || streams.length === 0) return null;

  if (streams.length === 1) {
    const c = streams[0];
    return (
      <a
        href={c.url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-space-xxs font-badge-status text-badge-status uppercase tracking-wider text-primary transition-colors hover:text-primary-fixed"
        onClick={(e) => e.stopPropagation()}
      >
        <Icone nome="play_circle" className="text-[14px]" />
        assistir
      </a>
    );
  }

  return (
    <details className={`group ${compacto ? "relative" : ""}`}>
      <summary
        className="inline-flex cursor-pointer list-none items-center gap-space-xxs font-badge-status text-badge-status uppercase tracking-wider text-primary transition-colors hover:text-primary-fixed [&::-webkit-details-marker]:hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <Icone nome="play_circle" className="text-[14px]" />
        assistir · {streams.length} canais
        <Icone
          nome="expand_more"
          className="text-[14px] transition-transform group-open:rotate-180"
        />
      </summary>
      <div
        className={`mt-space-xxs flex flex-col gap-[1px] rounded-lg border border-outline-variant/30 bg-surface-container-low p-space-xxs shadow-lg ${
          compacto ? "absolute right-0 z-20 w-56" : ""
        }`}
      >
        {streams.map((c) => (
          <LinhaCanal key={c.url} c={c} />
        ))}
      </div>
    </details>
  );
}
