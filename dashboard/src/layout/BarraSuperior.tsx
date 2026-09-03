/**
 * A barra superior fixa: onde voce esta, e se a API responde.
 *
 * O desenho do Stitch tem aqui tambem uma busca global, um sino de
 * notificacoes e um avatar de usuario. Os tres ficaram de fora: nao existe
 * endpoint de busca, nem de notificacao, nem autenticacao no projeto. Um campo
 * de busca que nao busca custa mais caro do que a falta dele.
 *
 * **A escolha de jogo saiu daqui.** Morava como uma fileira de chips fixa, e
 * isso parou de fazer sentido com as 73 wikis da Liquipedia no catalogo: os
 * chips quebravam a barra ou rolavam por cima dela, inclusive em telas como
 * Visao Geral e Assistente de IA que nao usam jogo nenhum. Virou
 * `<SeletorDeJogo />` (`componentes/SeletorDeJogo.tsx`), colocado so nas
 * quatro telas que de fato dependem do jogo - Partidas, Herois, Jogadores e
 * Previsao de Confronto.
 */

import { useLocation } from "react-router-dom";

import { useSaude } from "../api/consultas";
import { Icone } from "../componentes/base";
import { NAVEGACAO } from "./navegacao";

/** O rotulo da rota atual, para o "voce esta aqui" da esquerda. */
function useTituloDaRota(): string {
  const { pathname } = useLocation();

  if (pathname.startsWith("/steam/")) return "Detalhe do Jogo";
  if (pathname.startsWith("/partidas/")) return "Detalhe da Partida";

  const item = NAVEGACAO.find((i) => i.rota === pathname);
  return item?.rotulo ?? "Gaming Analytics";
}

export function BarraSuperior() {
  const titulo = useTituloDaRota();
  const saude = useSaude();
  const online = saude.data?.status === "ok";

  return (
    <header className="fixed left-72 right-0 top-0 z-40 flex h-16 items-center justify-between gap-space-base border-b border-outline-variant/30 bg-surface-container-lowest/95 px-space-lg backdrop-blur-md">
      <div className="flex min-w-0 items-center gap-space-sm">
        <Icone nome="chevron_right" className="text-[18px] text-outline" />
        <span className="truncate font-title-code text-title-code uppercase tracking-wider text-on-surface-variant">
          {titulo}
        </span>
      </div>

      <span
        className={[
          "inline-flex items-center gap-space-xs rounded px-space-md py-space-xs font-badge-status text-badge-status uppercase",
          online ? "bg-tertiary/10 text-tertiary" : "bg-error/10 text-error",
        ].join(" ")}
      >
        <span
          className={`h-2 w-2 rounded-full ${online ? "animate-pulse bg-tertiary" : "bg-error"}`}
          aria-hidden
        />
        {online ? "API no ar" : "API fora"}
      </span>
    </header>
  );
}
