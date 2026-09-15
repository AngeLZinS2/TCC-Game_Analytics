/**
 * A navegação principal no mobile: uma barra fixa embaixo, estilo app.
 *
 * A fileira de ícones da `BarraSuperior` tem seis alvos de 40px e não cabe num
 * cabeçalho de celular. Abaixo de `md` ela some e dá lugar a esta barra —
 * cinco destinos, rótulo curto, alvo alto o suficiente para o polegar. No
 * desktop (`md:` para cima) este componente não renderiza.
 *
 * "Perfil" ganhou conta de verdade na Fase 31 e entra na lista. O "APK" no
 * fim TEM destino (a landing estática `/mobile.html`), por isso também
 * entra — como `<a>` de verdade, fora da SPA.
 *
 * `pb-[env(safe-area-inset-bottom)]` reserva a faixa do gesto de home nos
 * aparelhos sem botão físico — sem isso o último item fica embaixo da barra do
 * sistema.
 */

import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Icone } from "@views/componentes/base";

interface ItemInferior {
  rota: string;
  /** Chave de traducao em `nav.inferior.<chave>`. */
  chave: string;
  icone: string;
  /** Rota-raiz: ativo por prefixo (E-Sports tem sub-rotas). */
  prefixo?: boolean;
}

const ITENS: ItemInferior[] = [
  { rota: "/painel", chave: "geral", icone: "space_dashboard" },
  { rota: "/catalogo", chave: "catalogo", icone: "sports_esports", prefixo: true },
  { rota: "/esports", chave: "esports", icone: "emoji_events", prefixo: true },
  { rota: "/recomendacoes", chave: "reviews", icone: "sentiment_satisfied" },
  { rota: "/assistente", chave: "ia", icone: "smart_toy" },
  { rota: "/perfil", chave: "perfil", icone: "account_circle" },
];

export function NavInferior() {
  const { t } = useTranslation();

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-50 flex border-t border-outline-variant/30 bg-surface-container-lowest/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
      aria-label={t("nav.navegacaoPrincipal")}
    >
      {ITENS.map((item) => (
        <NavLink
          key={item.chave}
          to={item.rota}
          end={item.rota === "/" || !item.prefixo}
          className={({ isActive }) =>
            [
              "flex flex-1 flex-col items-center justify-center gap-0.5 py-space-xs font-badge-status text-badge-status uppercase tracking-wide transition-colors",
              "min-h-[54px]",
              isActive
                ? "text-primary shadow-[inset_0_2px_0_0_#5a8cff]"
                : "text-on-surface-variant",
            ].join(" ")
          }
        >
          <Icone nome={item.icone} className="text-[22px]" />
          {t(`nav.inferior.${item.chave}`)}
        </NavLink>
      ))}

      <a
        href="/mobile.html"
        className="flex min-h-[54px] flex-1 flex-col items-center justify-center gap-0.5 py-space-xs font-badge-status text-badge-status uppercase tracking-wide text-on-surface-variant transition-colors"
      >
        <Icone nome="install_mobile" className="text-[22px]" />
        {t("nav.inferior.apk")}
      </a>
    </nav>
  );
}
