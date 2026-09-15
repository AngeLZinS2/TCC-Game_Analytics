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
import { useTranslation } from "react-i18next";

import { useJogosSteam, useJogosXbox } from "@models/api/consultas";
import { Icone } from "@views/componentes/base";
import { BannerDestaque } from "@views/componentes/BannerDestaque";
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
  const { t } = useTranslation();
  const { loja } = useParams();

  if (!loja || !IDS.includes(loja)) {
    return <Navigate to={`/catalogo/${LOJA_PADRAO}`} replace />;
  }
  const lojaAtual = loja as LojaId;

  // As capas de topo de Steam + Xbox - a mesma arte que os catálogos logo
  // abaixo mostram, sem chamada dedicada só pro banner.
  const steamTop = useJogosSteam({ ordenar_por: "jogadores", limite: 5 });
  const xboxTop = useJogosXbox({ ordenar_por: "game_pass", limite: 5 });
  const imagensHero = [
    ...(steamTop.data ?? []).map((j) => j.imagem_header),
    ...(xboxTop.data ?? []).map((j) => j.imagem_header),
  ].filter((url): url is string => Boolean(url));

  return (
    <div className="space-y-space-xl">
      <BannerDestaque imagens={imagensHero}>
        <span className="flex items-center gap-space-xxs font-label-caps text-label-caps uppercase tracking-widest text-primary">
          <Icone nome="grid_view" className="text-[15px]" />
          {t("catalogoLayout.hero.eyebrow")}
        </span>
        <h1 className="max-w-xl font-headline-lg text-headline-lg font-bold text-on-surface">
          {t("catalogoLayout.hero.titulo")}
          <span className="text-tertiary">{t("catalogoLayout.hero.tituloDestaque")}</span>
        </h1>
        <p className="max-w-lg font-body-sm text-body-sm text-on-surface-variant">
          {t("catalogoLayout.hero.descricao")}
        </p>
      </BannerDestaque>

      {/* ---------- barra de contexto ---------- */}
      <div className="flex flex-col gap-space-base border-b border-outline-variant/30 pb-space-base pt-space-base">
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
