/**
 * A barra superior unica: marca, navegacao e status da API.
 *
 * Ate aqui eram duas pecas - uma lateral fixa (marca + a lista de telas +
 * rodape de status) e esta, so com "onde voce esta" e o status resumido. A
 * lateral tomava 18rem de largura da tela inteira, o tempo todo, em toda
 * pagina - caro numa tela de dashboard que quer mostrar tabela e grafico
 * largos. Aqui a navegacao virou uma fileira de icones: cabe na mesma barra
 * horizontal que ja existia, sem gastar altura extra, e devolve a largura
 * inteira para o conteudo.
 *
 * **So icone perde o rotulo visivel** - por isso cada item tem uma dica
 * (`role="tooltip"`) que aparece no hover, e a `useTituloDaRota` (o "voce
 * esta aqui" de texto) continua existindo: e o que garante que a pagina
 * atual tem nome visivel sem precisar passar o mouse em nada.
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

import { Link, NavLink, useLocation } from "react-router-dom";

import { useDestaquesHome, useSaude } from "@models/api/consultas";
import { Icone } from "@views/componentes/base";
import { MenuEsports } from "@views/componentes/MenuEsports";
import { NAVEGACAO, type ItemNavegacao } from "./navegacao";
import { corDoJogo } from "@views/tema";
import { fmtQuando } from "@util/formatos";

/** O rotulo de cada sub-aba de E-Sports, para o "voce esta aqui". */
const ABAS_ESPORTS: Record<string, string> = {
  partidas: "Partidas",
  resultados: "Resultados",
  previsao: "Previsao",
  ranking: "Ranking",
  herois: "Herois",
  jogadores: "Jogadores",
};

/** O rotulo da rota atual, para o "voce esta aqui" da direita. */
function useTituloDaRota(): string {
  const { pathname } = useLocation();

  if (pathname.startsWith("/steam/")) return "Detalhe do Jogo";
  if (pathname.startsWith("/partidas/")) return "Detalhe da Partida";
  if (pathname.startsWith("/herois/")) return "Detalhe do Heroi";
  if (pathname.startsWith("/esports/")) {
    const aba = pathname.split("/")[3];
    const sufixo = aba && ABAS_ESPORTS[aba] ? ` · ${ABAS_ESPORTS[aba]}` : "";
    return `E-Sports${sufixo}`;
  }

  const item = NAVEGACAO.find((i) => i.rota === pathname);
  return item?.rotulo ?? "PlayDB";
}

/**
 * A dica que substitui o rotulo que a fileira de icones nao tem espaco para
 * mostrar direto. `pointer-events-none` porque ela nunca deve capturar o
 * clique - existe so para ler, o alvo do clique continua sendo o icone.
 */
function Dica({ texto, selo }: { texto: string; selo?: string }) {
  return (
    <span
      role="tooltip"
      className="pointer-events-none absolute left-1/2 top-full z-50 mt-space-xs flex -translate-x-1/2 items-center gap-space-xs whitespace-nowrap rounded bg-surface-container-highest px-space-sm py-space-xs font-title-code text-title-code text-on-surface opacity-0 shadow-lg transition-opacity delay-150 duration-150 group-hover:opacity-100"
    >
      {texto}
      {selo && (
        <span className="rounded bg-surface-container px-space-xxs py-[1px] font-badge-status text-badge-status text-primary">
          {selo}
        </span>
      )}
    </span>
  );
}

const BOTAO_NAV =
  "group relative flex h-10 w-10 items-center justify-center rounded-lg transition-colors";

function ItemNav({ item }: { item: ItemNavegacao }) {
  // E-Sports abre o menu de jogos no hover, em vez da dica de uma linha.
  if (item.menuEsports) {
    return <MenuEsports item={item} />;
  }

  // Sem rota: o icone existe para mostrar o produto inteiro, mas nao e um
  // link. `aria-disabled` em vez de `disabled` porque nao e um controle, e um
  // item de navegacao que ainda nao leva a lugar nenhum.
  if (item.rota === null) {
    return (
      <span className={`${BOTAO_NAV} cursor-not-allowed text-outline/50`} aria-disabled>
        <Icone nome={item.icone} className="text-[20px]" />
        <Dica texto={item.rotulo} selo={item.selo ?? "EM BREVE"} />
      </span>
    );
  }

  return (
    <NavLink
      to={item.rota}
      end={item.rota === "/"}
      className={({ isActive }) =>
        isActive
          ? `${BOTAO_NAV} bg-surface-container-high text-primary shadow-[inset_0_-2px_0_0_#5a8cff]`
          : `${BOTAO_NAV} text-on-surface-variant hover:bg-surface-container hover:text-on-surface`
      }
    >
      <Icone nome={item.icone} className="text-[20px]" />
      <Dica texto={item.rotulo} selo={item.selo} />
    </NavLink>
  );
}

/** Ticker de "acontecendo agora" — some no mobile e quando não há nada. */
function Ticker() {
  const { data } = useDestaquesHome();
  const itens = data?.ao_vivo.slice(0, 8) ?? [];
  if (itens.length === 0) return null;

  return (
    <div
      className="relative hidden min-w-0 flex-1 overflow-hidden border-x border-outline-variant/25 px-space-md lg:block"
      style={{
        maskImage:
          "linear-gradient(90deg, transparent, #000 24px, #000 calc(100% - 24px), transparent)",
      }}
    >
      <div className="ticker-fita inline-flex gap-space-xl whitespace-nowrap font-title-code text-title-code text-on-surface-variant">
        {[...itens, ...itens].map((c, i) => (
          <span key={i} className="inline-flex items-center gap-space-xs">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: corDoJogo(c.jogo) }}
              aria-hidden
            />
            <span className="text-on-surface">{c.equipe_a_nome}</span>
            <span className="text-outline">vs</span>
            <span className="text-on-surface">{c.equipe_b_nome}</span>
            <span className="text-outline">
              {c.ao_vivo ? "· ao vivo" : `· ${fmtQuando(c.inicio_previsto)}`}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

export function BarraSuperior() {
  const titulo = useTituloDaRota();
  const saude = useSaude();
  const online = saude.data?.status === "ok";

  return (
    <header className="fixed left-0 right-0 top-0 z-50 flex h-16 items-center gap-space-base border-b border-outline-variant/30 bg-surface-container-lowest/95 px-space-base backdrop-blur-md md:px-space-lg lg:left-60">
      {/* Marca e fileira de ícones: só até `lg` (no desktop, o trilho lateral). */}
      <Link to="/" className="flex shrink-0 items-center gap-space-sm lg:hidden">
        <Icone nome="stadia_controller" className="text-[24px] text-primary-container" />
        <span className="font-title-code text-title-code uppercase tracking-wider text-primary">
          PlayDB
        </span>
      </Link>

      <span className="hidden h-6 w-px shrink-0 bg-outline-variant/40 md:block lg:hidden" aria-hidden />

      <nav className="hidden items-center gap-space-xxs md:flex lg:hidden">
        {NAVEGACAO.map((item) => (
          <ItemNav key={item.rotulo} item={item} />
        ))}
        {/* Landing do app: página estática, fora da SPA — `<a>` de verdade. */}
        <a
          href="/mobile.html"
          className="group relative flex h-10 w-10 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface"
        >
          <Icone nome="install_mobile" className="text-[19px]" />
          <Dica texto="APK Mobile ↗" />
        </a>
      </nav>

      <span className="hidden h-6 w-px shrink-0 bg-outline-variant/40 md:block lg:hidden" aria-hidden />

      <div className="flex min-w-0 shrink-0 items-center gap-space-sm">
        <Icone nome="chevron_right" className="hidden text-[18px] text-outline md:block lg:hidden" />
        <span className="truncate font-title-code text-title-code uppercase tracking-wider text-on-surface-variant">
          {titulo}
        </span>
      </div>

      <Ticker />

      <div className="ml-auto flex shrink-0 items-center gap-space-sm lg:ml-0">
        <a
          href="/docs"
          target="_blank"
          rel="noreferrer"
          className="group relative hidden h-9 w-9 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface sm:flex"
        >
          <Icone nome="menu_book" className="text-[18px]" />
          <Dica texto="Documentação ↗" />
        </a>

        <span
          className={[
            "inline-flex items-center gap-space-xs rounded px-space-sm py-space-xs font-badge-status text-badge-status uppercase md:px-space-md",
            online ? "bg-tertiary/10 text-tertiary" : "bg-error/10 text-error",
          ].join(" ")}
          title={saude.data ? `latência ${saude.data.latenciaMs}ms` : undefined}
        >
          <span
            className={`h-2 w-2 rounded-full ${online ? "animate-pulse bg-tertiary" : "bg-error"}`}
            aria-hidden
          />
          <span className="hidden sm:inline">{online ? "API no ar" : "API fora"}</span>
        </span>
      </div>
    </header>
  );
}
