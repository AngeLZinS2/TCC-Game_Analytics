/**
 * A navegação principal no mobile: uma barra fixa embaixo, estilo app.
 *
 * A fileira de ícones da `BarraSuperior` tem seis alvos de 40px e não cabe num
 * cabeçalho de celular. Abaixo de `md` ela some e dá lugar a esta barra —
 * cinco destinos, rótulo curto, alvo alto o suficiente para o polegar. No
 * desktop (`md:` para cima) este componente não renderiza.
 *
 * "Perfil" fica de fora: depende de autenticação, que o projeto não tem, e um
 * sexto item sem destino só rouba espaço dos que funcionam.
 *
 * `pb-[env(safe-area-inset-bottom)]` reserva a faixa do gesto de home nos
 * aparelhos sem botão físico — sem isso o último item fica embaixo da barra do
 * sistema.
 */

import { NavLink } from "react-router-dom";

import { Icone } from "../componentes/base";

interface ItemInferior {
  rota: string;
  rotulo: string;
  icone: string;
  /** Rota-raiz: ativo por prefixo (E-Sports tem sub-rotas). */
  prefixo?: boolean;
}

const ITENS: ItemInferior[] = [
  { rota: "/", rotulo: "Geral", icone: "space_dashboard" },
  { rota: "/steam", rotulo: "Steam", icone: "sports_esports", prefixo: true },
  { rota: "/esports", rotulo: "E-Sports", icone: "emoji_events", prefixo: true },
  { rota: "/recomendacoes", rotulo: "Reviews", icone: "sentiment_satisfied" },
  { rota: "/assistente", rotulo: "IA", icone: "smart_toy" },
];

export function NavInferior() {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-50 flex border-t border-outline-variant/30 bg-surface-container-lowest/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
      aria-label="Navegação principal"
    >
      {ITENS.map((item) => (
        <NavLink
          key={item.rota}
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
          {item.rotulo}
        </NavLink>
      ))}
    </nav>
  );
}
