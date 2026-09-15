/**
 * A area E-Sports: uma barra de contexto (jogo + sub-abas) e, abaixo, a aba
 * ativa.
 *
 * Partidas, Resultados, Previsao, Ranking, Herois e Jogadores eram seis telas
 * separadas na barra, todas presas ao mesmo jogo escolhido. Aqui viram
 * sub-abas de `/esports/:jogo/:aba` - o jogo e o primeiro segmento da rota
 * (lido por `useJogoAtual`), a aba e o segundo.
 *
 * As telas grandes (Partidas e Previsao de Confronto) servem duas abas cada,
 * via a prop `secao`: o elemento fica no MESMO lugar da arvore entre as duas,
 * entao o React nao desmonta o componente ao trocar de aba e o estado dele
 * (filtros, par de times selecionado) sobrevive. E o que faz clicar numa linha
 * do Ranking e cair no simulador da aba Previsao com o time ja escolhido.
 */

import { Navigate, NavLink, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Icone } from "@views/componentes/base";
import { SeletorDeJogo } from "@views/componentes/SeletorDeJogo";
import { HeroisPagina } from "../Herois";
import { JogadoresPagina } from "../Jogadores";
import { PartidasPagina } from "../Partidas";
import { PrevisaoConfrontoPagina } from "../PrevisaoConfronto";

/** `id` casa com as chaves de `nav.esportsAbas.<id>` nos arquivos de traducao. */
const ABAS = [
  { id: "partidas", icone: "scoreboard" },
  { id: "resultados", icone: "flag" },
  { id: "previsao", icone: "swords", selo: "ML" },
  { id: "ranking", icone: "leaderboard" },
  { id: "herois", icone: "shield_person" },
  { id: "jogadores", icone: "group" },
] as const;

type AbaId = (typeof ABAS)[number]["id"];
const IDS: readonly string[] = ABAS.map((a) => a.id);

/** Jogo padrao quando a rota vem sem ele (`/esports`). */
const JOGO_PADRAO = "dota2";

export function EsportsLayout() {
  const { t } = useTranslation();
  const { jogo, aba } = useParams();

  if (!jogo) {
    return <Navigate to={`/esports/${JOGO_PADRAO}/partidas`} replace />;
  }
  if (!aba || !IDS.includes(aba)) {
    return <Navigate to={`/esports/${jogo}/partidas`} replace />;
  }
  const abaAtual = aba as AbaId;

  return (
    <div className="space-y-space-xl">
      {/* ---------- barra de contexto ---------- */}
      <div className="flex flex-col gap-space-base border-b border-outline-variant/30 pb-space-base pt-space-base">
        <div className="flex flex-wrap items-center gap-space-sm">
          <span className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface-variant">
            {t("nav.itens.esports")}
          </span>
          <Icone nome="chevron_right" className="text-[18px] text-outline" />
          <SeletorDeJogo
            disponivel={(j) => j.partidas > 0 || j.equipes > 0 || j.agenda > 0}
          />
        </div>

        <nav className="rolagem-discreta -mb-space-xxs flex gap-space-xxs overflow-x-auto">
          {ABAS.map((item) => (
            <NavLink
              key={item.id}
              to={`/esports/${jogo}/${item.id}`}
              className={({ isActive }) =>
                [
                  "flex shrink-0 items-center gap-space-xs rounded-t px-space-md py-space-sm font-title-code text-title-code uppercase tracking-wider transition-colors",
                  isActive
                    ? "bg-surface-container-high text-primary shadow-[inset_0_-2px_0_0_#5a8cff]"
                    : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface",
                ].join(" ")
              }
            >
              <Icone nome={item.icone} className="text-[16px]" />
              {t(`nav.esportsAbas.${item.id}`)}
              {"selo" in item && item.selo && (
                <span className="rounded bg-surface-container px-space-xxs py-[1px] font-badge-status text-badge-status text-primary">
                  {item.selo}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
      </div>

      {/* ---------- aba ativa ---------- */}
      <div className="space-y-space-xl">
        {(abaAtual === "partidas" || abaAtual === "resultados") && (
          <PartidasPagina secao={abaAtual} />
        )}
        {(abaAtual === "previsao" || abaAtual === "ranking") && (
          <PrevisaoConfrontoPagina secao={abaAtual} />
        )}
        {abaAtual === "herois" && <HeroisPagina />}
        {abaAtual === "jogadores" && <JogadoresPagina />}
      </div>
    </div>
  );
}
