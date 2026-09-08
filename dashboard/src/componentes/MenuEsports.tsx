/**
 * O menu de jogos da entrada "E-Sports" da barra superior.
 *
 * Substitui a dica simples dos outros icones: passar o mouse (ou focar pelo
 * teclado) abre a lista de jogos com conteudo de esports, e cada um leva para
 * `/esports/<jogo>/partidas`. O clique direto no icone vai para a area no
 * jogo atual - o menu e um atalho para trocar de jogo sem entrar primeiro.
 *
 * O vao entre o icone e o painel e preenchido por `padding-top`, nao por
 * `margin` - uma margem criaria uma faixa sem dono onde o `mouseleave`
 * dispararia no meio do caminho ate a lista (a causa classica de um menu por
 * hover "fechar sozinho").
 */

import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { useJogosDisponiveis } from "../api/consultas";
import type { JogoDisponivel } from "../api/tipos";
import { corDoJogo } from "../tema";
import type { ItemNavegacao } from "../layout/navegacao";
import { Icone } from "./base";

const BOTAO_NAV =
  "group relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors";

/** Um jogo aparece no menu quando tem qualquer coisa de esports coletada. */
function temEsports(jogo: JogoDisponivel): boolean {
  return jogo.partidas > 0 || jogo.equipes > 0 || jogo.agenda > 0;
}

/** O que a linha de um jogo resume, na ordem em que importa. */
function oQueTem(jogo: JogoDisponivel): string {
  return [
    jogo.partidas ? `${jogo.partidas} partidas` : null,
    jogo.agenda ? `${jogo.agenda} na agenda` : null,
    jogo.equipes ? `${jogo.equipes} equipes` : null,
    jogo.personagens ? `${jogo.personagens} personagens` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function MenuEsports({ item }: { item: ItemNavegacao }) {
  const jogos = useJogosDisponiveis();
  const { pathname } = useLocation();
  const [aberto, setAberto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);

  const naArea = pathname.startsWith("/esports");
  const jogoAtual = naArea ? pathname.split("/")[2] : undefined;

  useEffect(() => {
    if (!aberto) return;
    function aoClicarFora(evento: MouseEvent) {
      if (!raiz.current?.contains(evento.target as Node)) setAberto(false);
    }
    function aoTeclarEscape(evento: KeyboardEvent) {
      if (evento.key === "Escape") setAberto(false);
    }
    document.addEventListener("mousedown", aoClicarFora);
    document.addEventListener("keydown", aoTeclarEscape);
    return () => {
      document.removeEventListener("mousedown", aoClicarFora);
      document.removeEventListener("keydown", aoTeclarEscape);
    };
  }, [aberto]);

  // Fecha ao navegar - senao o painel fica aberto por cima da tela nova.
  useEffect(() => setAberto(false), [pathname]);

  const lista = (jogos.data ?? [])
    .filter(temEsports)
    .sort((a, b) => b.partidas - a.partidas || b.agenda - a.agenda || b.equipes - a.equipes);

  return (
    <div
      ref={raiz}
      className="relative"
      onMouseEnter={() => setAberto(true)}
      onMouseLeave={() => setAberto(false)}
    >
      <NavLink
        to={item.rota ?? "/esports"}
        onFocus={() => setAberto(true)}
        aria-haspopup="menu"
        aria-expanded={aberto}
        className={({ isActive }) =>
          isActive || naArea
            ? `${BOTAO_NAV} bg-surface-container-high text-primary shadow-[inset_0_-2px_0_0_#00e5ff]`
            : `${BOTAO_NAV} text-on-surface-variant hover:bg-surface-container hover:text-on-surface`
        }
      >
        <Icone nome={item.icone} className="text-[20px]" />
      </NavLink>

      {aberto && (
        <div className="absolute left-1/2 top-full z-50 -translate-x-1/2 pt-space-xs">
          <div
            role="menu"
            aria-label="Jogos de e-sports"
            className="rolagem-discreta flex max-h-[70vh] w-64 flex-col gap-space-xxs overflow-y-auto rounded-lg border border-outline-variant/30 bg-surface-container-low p-space-xs shadow-2xl"
          >
            <span className="px-space-sm py-space-xxs font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {item.rotulo}
            </span>

            {jogos.isPending && (
              <span className="px-space-sm py-space-xs font-body-sm text-body-sm text-outline">
                Carregando…
              </span>
            )}

            {jogos.data && lista.length === 0 && (
              <span className="px-space-sm py-space-xs font-body-sm text-body-sm text-outline">
                Nada coletado ainda.
              </span>
            )}

            {lista.map((jogo) => {
              const ativo = jogo.codigo === jogoAtual;
              return (
                <Link
                  key={jogo.codigo}
                  to={`/esports/${jogo.codigo}/partidas`}
                  role="menuitem"
                  aria-current={ativo ? "page" : undefined}
                  className={[
                    "flex flex-col items-start gap-0.5 rounded px-space-sm py-space-xs text-left transition-colors",
                    ativo ? "bg-surface-container-high" : "hover:bg-surface-container-high",
                  ].join(" ")}
                >
                  <span className="flex items-center gap-space-xs font-title-code text-title-code text-on-surface">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: corDoJogo(jogo.codigo) }}
                      aria-hidden
                    />
                    <span className="truncate">{jogo.nome}</span>
                  </span>
                  <span className="pl-[16px] font-label-caps text-label-caps text-outline">
                    {oQueTem(jogo)}
                  </span>
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
