/** A barra lateral fixa: marca, navegacao e o rodape de status da API. */

import { NavLink } from "react-router-dom";

import { useSaude } from "../api/consultas";
import { Icone } from "../componentes/base";
import { NAVEGACAO, type ItemNavegacao } from "./navegacao";

function Item({ item }: { item: ItemNavegacao }) {
  const comum =
    "flex items-center gap-space-sm rounded px-space-md py-space-sm font-title-code text-title-code transition-colors";

  // Sem rota: a linha existe para mostrar o produto inteiro, mas nao e um link.
  // `aria-disabled` em vez de `disabled` porque nao e um controle, e um item de
  // navegacao que ainda nao leva a lugar nenhum.
  if (item.rota === null) {
    return (
      <span
        className={`${comum} cursor-not-allowed text-outline/60`}
        aria-disabled
        title="Tela desenhada, ainda sem backend"
      >
        <Icone nome={item.icone} />
        <span className="flex-1">{item.rotulo}</span>
        <span className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status text-outline">
          {item.selo ?? "EM BREVE"}
        </span>
      </span>
    );
  }

  return (
    <NavLink
      to={item.rota}
      end={item.rota === "/"}
      className={({ isActive }) =>
        isActive
          ? `${comum} bg-surface-container-high font-bold text-primary shadow-[inset_3px_0_0_0_#00e5ff]`
          : `${comum} text-on-surface-variant hover:bg-surface-container hover:text-on-surface`
      }
    >
      <Icone nome={item.icone} />
      <span className="flex-1">{item.rotulo}</span>
      {item.selo && (
        <span className="rounded bg-surface-container-highest px-space-xs py-space-xxs font-badge-status text-badge-status text-primary">
          {item.selo}
        </span>
      )}
    </NavLink>
  );
}

/**
 * O rodape do desenho traz "Sistemas operacionais" e uma latencia.
 *
 * No mockup os dois sao enfeite. Aqui sao o resultado real do `/health`: o
 * ponto verde so acende se o Postgres respondeu, e o numero e o tempo que a
 * chamada levou. Um indicador de status que esta sempre verde nao e um
 * indicador de status.
 */
function StatusApi() {
  const saude = useSaude();
  const ok = saude.data?.status === "ok";

  const cor = saude.isPending
    ? "bg-outline"
    : ok
      ? "bg-tertiary-container"
      : "bg-error";

  const texto = saude.isPending
    ? "Verificando"
    : ok
      ? "Sistemas operacionais"
      : saude.data?.banco === false
        ? "Banco fora"
        : "API fora";

  return (
    <div className="space-y-space-sm bg-surface-container-low/90 p-space-base">
      <div className="flex items-center justify-between text-on-surface-variant">
        <div className="flex items-center gap-space-xs">
          <span className="relative flex h-2.5 w-2.5">
            {ok && (
              <span
                className={`absolute inline-flex h-full w-full animate-ping rounded-full ${cor} opacity-75`}
                aria-hidden
              />
            )}
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${cor}`} />
          </span>
          <span
            className={`font-label-caps text-label-caps uppercase ${ok ? "text-tertiary" : "text-on-surface-variant"}`}
          >
            {texto}
          </span>
        </div>
        <span className="font-title-code text-title-code text-primary">
          {saude.data ? `${saude.data.latenciaMs}ms` : "—"}
        </span>
      </div>

      <div className="flex items-center justify-between font-label-caps text-label-caps text-outline">
        <span>Stream feed</span>
        <a
          className="font-title-code text-title-code text-on-surface-variant transition-colors hover:text-primary"
          href="/docs"
          target="_blank"
          rel="noreferrer"
        >
          Documentação ↗
        </a>
      </div>
    </div>
  );
}

export function BarraLateral() {
  const online = useSaude().data?.status === "ok";

  return (
    <aside className="fixed left-0 top-0 z-50 flex h-screen w-72 flex-col bg-surface-container-lowest shadow-[0_1px_8px_rgba(0,0,0,0.5)]">
      <div className="flex h-16 items-center justify-between bg-surface-container-low/60 px-space-base">
        <div className="flex items-center gap-space-sm">
          <Icone nome="stadia_controller" className="text-[24px] text-primary-container" />
          <div className="flex flex-col">
            <span className="font-title-code text-title-code uppercase tracking-wider text-primary">
              Nexus // Hub
            </span>
            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Gaming Analytics · TCC
            </span>
          </div>
        </div>
        {/* O ponto so pulsa quando a API respondeu: e status, nao enfeite. */}
        {online && (
          <span
            className="h-2 w-2 animate-ping rounded-full bg-primary-container"
            aria-hidden
          />
        )}
      </div>

      <div className="px-space-base py-space-sm">
        <div className="flex items-center justify-between rounded bg-surface-container px-space-sm py-space-xs font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <span>Painéis</span>
          <span
            className={`font-title-code text-title-code ${online ? "text-primary" : "text-outline"}`}
          >
            {online ? "SYS.ON" : "SYS.OFF"}
          </span>
        </div>
      </div>

      <nav className="rolagem-discreta flex-1 space-y-space-xxs overflow-y-auto px-space-sm">
        {NAVEGACAO.map((item) => (
          <Item key={item.rotulo} item={item} />
        ))}
      </nav>

      <StatusApi />
    </aside>
  );
}
