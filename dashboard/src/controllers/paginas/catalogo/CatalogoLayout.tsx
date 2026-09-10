/**
 * A area Catalogo de Jogos: uma barra de contexto (nome + abas por loja) e,
 * abaixo, a aba ativa.
 *
 * "Jogos da Steam" era uma tela so. Aqui vira a aba Steam de `/catalogo/:loja`,
 * ao lado de PlayStation e Xbox - o mesmo desenho de sub-abas do `EsportsLayout`
 * (a loja e o segmento da rota, o `<NavLink>` cuida do estado ativo).
 *
 * Xbox e uma vitrine rasa de proposito: nao ha CCU publico nem texto de
 * avaliacao em API gratuita da Microsoft, entao a aba mostra ficha + preco +
 * selo do Game Pass, e nada de grafico de jogadores ou modelo de ML.
 * PlayStation depende da aprovacao da chave do PlatPrices - por ora, "em breve".
 */

import { Navigate, NavLink, useParams } from "react-router-dom";

import { Icone } from "@views/componentes/base";
import { SteamPagina } from "../Steam";
import { XboxCatalogo } from "./XboxCatalogo";
import { PlayStationEmBreve } from "./PlayStationEmBreve";

const LOJAS = [
  { id: "steam", rotulo: "Steam", icone: "sports_esports" },
  { id: "playstation", rotulo: "PlayStation", icone: "stadia_controller" },
  { id: "xbox", rotulo: "Xbox", icone: "gamepad" },
] as const;

type LojaId = (typeof LOJAS)[number]["id"];
const IDS: readonly string[] = LOJAS.map((l) => l.id);

const LOJA_PADRAO: LojaId = "steam";

export function CatalogoLayout() {
  const { loja } = useParams();

  if (!loja || !IDS.includes(loja)) {
    return <Navigate to={`/catalogo/${LOJA_PADRAO}`} replace />;
  }
  const lojaAtual = loja as LojaId;

  return (
    <div className="space-y-space-xl">
      {/* ---------- barra de contexto ---------- */}
      <div className="flex flex-col gap-space-base border-b border-outline-variant/30 pb-space-base pt-space-base">
        <div className="flex flex-wrap items-center gap-space-sm">
          <span className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface-variant">
            Catálogo de Jogos
          </span>
        </div>

        <nav className="rolagem-discreta -mb-space-xxs flex gap-space-xxs overflow-x-auto">
          {LOJAS.map((l) => (
            <NavLink
              key={l.id}
              to={`/catalogo/${l.id}`}
              className={({ isActive }) =>
                [
                  "flex shrink-0 items-center gap-space-xs rounded-t px-space-md py-space-sm font-title-code text-title-code uppercase tracking-wider transition-colors",
                  isActive
                    ? "bg-surface-container-high text-primary shadow-[inset_0_-2px_0_0_#5a8cff]"
                    : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
                ].join(" ")
              }
            >
              <Icone nome={l.icone} className="text-[16px]" />
              {l.rotulo}
            </NavLink>
          ))}
        </nav>
      </div>

      {/* ---------- aba ativa ---------- */}
      <div className="space-y-space-xl">
        {lojaAtual === "steam" && <SteamPagina />}
        {lojaAtual === "xbox" && <XboxCatalogo />}
        {lojaAtual === "playstation" && <PlayStationEmBreve />}
      </div>
    </div>
  );
}
