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
import { useTranslation } from "react-i18next";

import { useJogosDisponiveis, useSouAdmin } from "@models/api/consultas";
import { useUsuario } from "@models/conta/contexto";
import { Icone } from "@views/componentes/base";
import { SeletorIdioma } from "@views/componentes/SeletorIdioma";
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
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const jogos = useJogosDisponiveis();
  const { usuario } = useUsuario();
  const souAdmin = useSouAdmin();

  const lista = (jogos.data ?? [])
    .filter((j) => j.partidas > 0 || j.equipes > 0 || j.agenda > 0)
    .sort((a, b) => b.partidas - a.partidas || b.agenda - a.agenda || b.equipes - a.equipes)
    .slice(0, 8);

  const jogoAtual = pathname.startsWith("/esports/") ? pathname.split("/")[2] : undefined;

  return (
    <aside className="fixed left-0 top-0 z-40 hidden h-screen w-60 flex-col border-r border-outline-variant/25 bg-surface-container-lowest px-space-sm py-space-base lg:flex">
      <NavLink to="/painel" className="mb-space-lg flex items-center gap-space-sm px-space-sm">
        <img src="/logo-icone.png" alt="" className="h-7 w-7 shrink-0 object-contain" />
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
                  {t(`nav.itens.${item.chave}`)}
                </span>
                {lista.length === 0 && (
                  <span className="block px-space-sm py-space-xs font-body-sm text-body-sm text-outline">
                    {t("comum.nadaColetadoAinda")}
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
                    {t("nav.verVisaoGeral")}
                  </NavLink>
                )}
                <span className="mt-space-sm block px-space-sm pb-space-xxs font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  {t("nav.mais")}
                </span>
              </div>
            );
          }

          if (item.rota === null) {
            return (
              <span
                key={item.chave}
                className={`${ITEM} cursor-not-allowed text-outline/50`}
                aria-disabled
              >
                <Icone nome={item.icone} className="text-[19px]" />
                <span className="truncate">{t(`nav.itens.${item.chave}`)}</span>
                <span className="ml-auto rounded bg-surface-container px-space-xxs py-[1px] font-badge-status text-badge-status text-outline">
                  {t("comum.emBreve")}
                </span>
              </span>
            );
          }

          // "Perfil" é o mesmo link de sempre, mas logado ele vira a
          // identidade da conta (foto + nome) em vez de ícone genérico +
          // rótulo — sem duplicar em outro lugar da barra.
          if (item.rota === "/perfil" && usuario) {
            return (
              <NavLink
                key={item.chave}
                to={item.rota}
                className={({ isActive }) => `${ITEM} ${isActive ? ATIVO : INATIVO}`}
              >
                {({ isActive }) => (
                  <>
                    {marcadorAtivo(isActive)}
                    {usuario.photoURL ? (
                      <img
                        src={usuario.photoURL}
                        alt=""
                        className="h-6 w-6 shrink-0 rounded-full object-cover"
                      />
                    ) : (
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary-container/20 font-label-caps text-label-caps text-primary">
                        {(usuario.displayName ?? usuario.email ?? "?").charAt(0).toUpperCase()}
                      </span>
                    )}
                    <span className="min-w-0 flex-1 truncate">
                      {usuario.displayName ?? usuario.email?.split("@")[0] ?? t("nav.itens.perfil")}
                    </span>
                  </>
                )}
              </NavLink>
            );
          }

          return (
            <NavLink
              key={item.chave}
              to={item.rota}
              end={item.rota === "/painel"}
              className={({ isActive }) => `${ITEM} ${isActive ? ATIVO : INATIVO}`}
            >
              {({ isActive }) => (
                <>
                  {marcadorAtivo(isActive)}
                  <Icone nome={item.icone} className="text-[19px]" />
                  <span className="truncate">{t(`nav.itens.${item.chave}`)}</span>
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

        {/* Painel Admin — não é um item de `NAVEGACAO`: só existe pra conta
            do dono do site (`ADMIN_FIREBASE_UIDS` no backend). Ninguém mais
            vê este link, nem logado; quem tentar `/admin` na unha esbarra no
            403 do backend do mesmo jeito. */}
        {souAdmin.data?.admin && (
          <NavLink
            to="/admin"
            className={({ isActive }) => `${ITEM} ${isActive ? ATIVO : INATIVO}`}
          >
            {({ isActive }) => (
              <>
                {marcadorAtivo(isActive)}
                <Icone nome="admin_panel_settings" className="text-[19px]" />
                <span className="truncate">{t("nav.painelAdmin")}</span>
              </>
            )}
          </NavLink>
        )}

        {/* Sai da SPA: `/mobile.html` é página estática (Vite `public/`). Por
            isso `<a>` de verdade, não `<NavLink>`. */}
        <a
          href="/mobile.html"
          className={`${ITEM} ${INATIVO} mt-space-sm border-t border-outline-variant/25 pt-space-md`}
        >
          <Icone nome="install_mobile" className="text-[19px]" />
          <span className="truncate">{t("nav.apkMobile")}</span>
          <Icone nome="arrow_outward" className="ml-auto text-[15px] opacity-50" />
        </a>

        <div className="flex items-center justify-between px-space-sm pt-space-xs">
          <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
            {t("idioma.nome")}
          </span>
          <SeletorIdioma />
        </div>
      </nav>
    </aside>
  );
}
