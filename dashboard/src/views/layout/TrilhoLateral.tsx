/**
 * O trilho lateral fixo — só no desktop (`lg+`).
 *
 * A navegação da `BarraSuperior` é uma fileira de ícones sem rótulo, boa para
 * caber numa barra estreita mas ruim para orientar. Numa tela larga sobra
 * espaço: aqui a mesma navegação vira uma coluna rotulada, com E-Sports
 * expandido nos jogos que têm dado coletado — cada um com a cor do jogo no
 * marcador.
 *
 * Abaixo de `lg` este componente não renderiza; ali valem a `BarraSuperior`
 * (tablet) e a `NavInferior` (celular).
 */

import { NavLink, useLocation } from "react-router-dom";

import { useJogosDisponiveis } from "@models/api/consultas";
import { Icone } from "@views/componentes/base";
import { corDoJogo } from "@views/tema";
import { NAVEGACAO } from "./navegacao";

const ITEM =
  "group relative flex items-center gap-space-sm rounded-lg px-space-sm py-[9px] font-body-md text-body-sm font-medium transition-colors";
const ATIVO = "bg-surface-container-high text-primary";
const INATIVO = "text-on-surface-variant hover:bg-surface-container hover:text-on-surface";

function marcadorAtivo(ativo: boolean) {
  return ativo ? (
    <span
      className="absolute -left-space-xs top-[9px] bottom-[9px] w-[3px] rounded-r bg-primary-container"
      aria-hidden
    />
  ) : null;
}

export function TrilhoLateral() {
  const { pathname } = useLocation();
  const jogos = useJogosDisponiveis();

  const lista = (jogos.data ?? [])
    .filter((j) => j.partidas > 0 || j.equipes > 0 || j.agenda > 0)
    .sort((a, b) => b.partidas - a.partidas || b.agenda - a.agenda || b.equipes - a.equipes)
    .slice(0, 8);

  const jogoAtual = pathname.startsWith("/esports/") ? pathname.split("/")[2] : undefined;

  return (
    <aside className="fixed left-0 top-0 z-40 hidden h-screen w-60 flex-col border-r border-outline-variant/25 bg-surface-container-lowest px-space-sm py-space-base lg:flex">
      <NavLink to="/" className="mb-space-lg flex items-center gap-space-sm px-space-sm">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-secondary-fixed-dim font-title-code text-title-code font-semibold text-on-secondary">
          P
        </span>
        <span className="font-headline-sm text-headline-sm font-bold tracking-tight text-on-surface">
          PlayDB
        </span>
      </NavLink>

      <nav className="flex min-h-0 flex-1 flex-col gap-[2px] overflow-y-auto rolagem-discreta">
        {NAVEGACAO.map((item) => {
          if (item.menuEsports) {
            const naArea = pathname.startsWith("/esports");
            return (
              <div key="esports">
                <span className="mt-space-sm block px-space-sm pb-space-xxs font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  {item.rotulo}
                </span>
                {lista.length === 0 && (
                  <span className="block px-space-sm py-space-xs font-body-sm text-body-sm text-outline">
                    Nada coletado ainda.
                  </span>
                )}
                {lista.map((jogo) => {
                  const ativo = jogoAtual === jogo.codigo;
                  return (
                    <NavLink
                      key={jogo.codigo}
                      to={`/esports/${jogo.codigo}/partidas`}
                      className={`${ITEM} ${ativo ? ATIVO : INATIVO} pl-space-base`}
                    >
                      {marcadorAtivo(ativo)}
                      <span
                        className="h-[3px] w-4 shrink-0 rounded-full"
                        style={{ background: corDoJogo(jogo.codigo) }}
                        aria-hidden
                      />
                      <span className="truncate">{jogo.nome}</span>
                    </NavLink>
                  );
                })}
                {!naArea && lista.length > 0 && (
                  <NavLink
                    to="/esports"
                    className={`${ITEM} ${INATIVO} pl-space-base font-body-sm text-outline`}
                  >
                    <span className="w-4 shrink-0" aria-hidden />
                    ver visão geral
                  </NavLink>
                )}
                <span className="mt-space-sm block px-space-sm pb-space-xxs font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  Mais
                </span>
              </div>
            );
          }

          if (item.rota === null) {
            return (
              <span
                key={item.rotulo}
                className={`${ITEM} cursor-not-allowed text-outline/50`}
                aria-disabled
              >
                <Icone nome={item.icone} className="text-[19px]" />
                <span className="truncate">{item.rotulo}</span>
                <span className="ml-auto rounded bg-surface-container px-space-xxs py-[1px] font-badge-status text-badge-status text-outline">
                  em breve
                </span>
              </span>
            );
          }

          return (
            <NavLink
              key={item.rotulo}
              to={item.rota}
              end={item.rota === "/"}
              className={({ isActive }) => `${ITEM} ${isActive ? ATIVO : INATIVO}`}
            >
              {({ isActive }) => (
                <>
                  {marcadorAtivo(isActive)}
                  <Icone nome={item.icone} className="text-[19px]" />
                  <span className="truncate">{item.rotulo}</span>
                  {item.selo && (
                    <span className="ml-auto rounded bg-surface-container-high px-space-xxs py-[1px] font-badge-status text-badge-status text-primary">
                      {item.selo}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          );
        })}

        {/* Sai da SPA: `/mobile.html` é página estática (Vite `public/`). Por
            isso `<a>` de verdade, não `<NavLink>`. */}
        <a
          href="/mobile.html"
          className={`${ITEM} ${INATIVO} mt-space-sm border-t border-outline-variant/25 pt-space-md`}
        >
          <Icone nome="install_mobile" className="text-[19px]" />
          <span className="truncate">APK Mobile</span>
          <Icone nome="arrow_outward" className="ml-auto text-[15px] opacity-50" />
        </a>
      </nav>
    </aside>
  );
}
