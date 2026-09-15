/**
 * A area Catalogo de Jogos: o banner de contexto (titulo, lojas, periodo e
 * estatisticas de cobertura) e, abaixo, a aba ativa.
 *
 * "Jogos da Steam" era uma tela so. Aqui vira a aba Steam de `/catalogo/:loja`,
 * ao lado de PlayStation e Xbox - a loja e o segmento da rota, o `<NavLink>`
 * cuida do estado ativo.
 *
 * O seletor de periodo mora aqui (e nao dentro da aba) porque o desenho o
 * coloca junto das lojas, mas quem consome sao as series da aba Steam: ele
 * desce por prop. Nas abas sem serie historica (Xbox, PlayStation) ele nem
 * aparece - um controle que nao muda nada seria pior que a ausencia dele.
 *
 * Xbox e uma vitrine rasa de proposito: nao ha CCU publico nem texto de
 * avaliacao em API gratuita da Microsoft, entao a aba mostra ficha + preco +
 * selo do Game Pass, e nada de grafico de jogadores ou modelo de ML.
 * PlayStation depende da aprovacao da chave do PlatPrices - por ora, "em breve".
 */

import { useState } from "react";
import { Navigate, NavLink, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useJogosSteam, useJogosXbox, useVisaoGeral } from "@models/api/consultas";
import { Icone } from "@views/componentes/base";
import { BannerDestaque } from "@views/componentes/BannerDestaque";
import { CaixaEstatistica, EstatisticasGerais } from "@views/componentes/EstatisticasGerais";
import { SeletorPeriodo, type Periodo } from "@views/componentes/SeletorPeriodo";
import { fmtCurto, fmtNumero } from "@util/formatos";
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

const MS_POR_DIA = 86_400_000;

export function CatalogoLayout() {
  const { t } = useTranslation();
  const { loja } = useParams();
  const [periodo, setPeriodo] = useState<Periodo>(7);

  const visaoGeral = useVisaoGeral();
  // As capas de topo de Steam + Xbox - a mesma arte que os catálogos logo
  // abaixo mostram, sem chamada dedicada só pro banner.
  const steamTop = useJogosSteam({ ordenar_por: "jogadores", limite: 5 });
  const xboxTop = useJogosXbox({ ordenar_por: "game_pass", limite: 5 });

  if (!loja || !IDS.includes(loja)) {
    return <Navigate to={`/catalogo/${LOJA_PADRAO}`} replace />;
  }
  const lojaAtual = loja as LojaId;

  const imagensHero = [
    ...(steamTop.data ?? []).map((j) => j.imagem_header),
    ...(xboxTop.data ?? []).map((j) => j.imagem_header),
  ].filter((url): url is string => Boolean(url));

  const desde = visaoGeral.data?.historico_steam_desde;
  const diasDisponiveis = desde
    ? (Date.now() - new Date(desde).getTime()) / MS_POR_DIA
    : null;

  return (
    <div className="space-y-space-xl">
      <div className="grid gap-space-base xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <BannerDestaque imagens={imagensHero}>
          <div className="flex items-center gap-space-sm">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-container/20 text-primary">
              <Icone nome="sports_esports" className="text-[22px]" />
            </span>
            <h1 className="font-headline-lg text-headline-lg font-bold uppercase tracking-wide text-on-surface">
              {t("nav.itens.catalogo")}
            </h1>
          </div>
          <p className="max-w-lg font-body-sm text-body-sm text-on-surface-variant">
            {t("catalogoLayout.hero.descricao")}
          </p>

          <div className="flex flex-wrap items-center gap-space-sm pt-space-sm">
            <nav className="rolagem-discreta flex gap-space-xxs overflow-x-auto">
              {LOJAS.map((l) => (
                <NavLink
                  key={l.id}
                  to={`/catalogo/${l.id}`}
                  className={({ isActive }) =>
                    [
                      "flex shrink-0 items-center gap-space-xs rounded-full px-space-md py-space-xs font-title-code text-title-code uppercase tracking-wider transition-colors",
                      isActive
                        ? "bg-primary-container text-on-primary"
                        : "bg-surface-container-lowest/80 text-on-surface-variant ring-1 ring-outline-variant/30 hover:bg-surface-container-high/60 hover:text-on-surface",
                    ].join(" ")
                  }
                >
                  <Icone nome={l.icone} className="text-[16px]" />
                  {l.rotulo}
                </NavLink>
              ))}
            </nav>

            {/* Só a aba Steam tem série histórica - nas outras o seletor não
                teria o que recortar. */}
            {lojaAtual === "steam" && (
              <SeletorPeriodo
                valor={periodo}
                aoMudar={setPeriodo}
                diasDisponiveis={diasDisponiveis}
              />
            )}
          </div>
        </BannerDestaque>

        <EstatisticasGerais titulo={t("catalogoLayout.estatisticas.titulo")}>
          <CaixaEstatistica
            icone="sports_esports"
            valor={fmtNumero(visaoGeral.data?.jogos_steam)}
            rotulo={t("catalogoLayout.estatisticas.jogosNoCatalogo")}
          />
          <CaixaEstatistica
            icone="group"
            valor={fmtCurto(visaoGeral.data?.jogadores_simultaneos_total)}
            rotulo={t("catalogoLayout.estatisticas.jogadoresAgora")}
            acento="text-tertiary"
          />
          <CaixaEstatistica
            icone="gamepad"
            valor={fmtNumero(visaoGeral.data?.jogos_xbox)}
            rotulo={t("catalogoLayout.estatisticas.jogosXbox")}
            acento="text-secondary"
          />
          <CaixaEstatistica
            icone="monitoring"
            valor={
              diasDisponiveis === null
                ? "—"
                : t("catalogoLayout.estatisticas.diasValor", {
                    dias: Math.floor(diasDisponiveis),
                  })
            }
            rotulo={t("catalogoLayout.estatisticas.historico")}
            acento="text-primary"
          />
        </EstatisticasGerais>
      </div>

      {/* ---------- aba ativa ---------- */}
      <div className="space-y-space-xl">
        {lojaAtual === "steam" && <SteamPagina periodo={periodo} />}
        {lojaAtual === "xbox" && <XboxCatalogo />}
        {lojaAtual === "playstation" && <PlayStationEmBreve />}
      </div>
    </div>
  );
}
