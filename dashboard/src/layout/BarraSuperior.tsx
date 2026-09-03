/**
 * A barra superior fixa: onde voce esta, e sobre qual jogo.
 *
 * O desenho do Stitch tem aqui tambem uma busca global, um sino de
 * notificacoes e um avatar de usuario. Os tres ficaram de fora: nao existe
 * endpoint de busca, nem de notificacao, nem autenticacao no projeto. Um campo
 * de busca que nao busca custa mais caro do que a falta dele.
 */

import { useLocation } from "react-router-dom";

import { useJogosDisponiveis, useSaude } from "../api/consultas";
import { Icone } from "../componentes/base";
import { corDoJogo } from "../tema";
import { useJogoAtual } from "./JogoAtual";
import { NAVEGACAO } from "./navegacao";

/** O rotulo da rota atual, para o "voce esta aqui" da esquerda. */
function useTituloDaRota(): string {
  const { pathname } = useLocation();

  if (pathname.startsWith("/steam/")) return "Detalhe do Jogo";
  if (pathname.startsWith("/partidas/")) return "Detalhe da Partida";

  const item = NAVEGACAO.find((i) => i.rota === pathname);
  return item?.rotulo ?? "Gaming Analytics";
}

/**
 * Chips de jogo do dominio de partidas.
 *
 * **Um jogo so e desabilitado quando nao tem NADA.** A regra era
 * `partidas === 0`, e ela ficou errada quando as 73 wikis da Liquipedia
 * entraram: Counter-Strike tem 1.409 equipes e 54 confrontos agendados e zero
 * partidas coletadas - o chip dele aparecia inerte, e nao havia como abrir a
 * agenda que existe. Agora "vazio" significa vazio em todas as fontes, e o
 * `title` diz o que cada jogo de fato tem.
 *
 * A lista rola na horizontal porque passou de tres jogos para dezenas. Sem a
 * rolagem, os chips empurram a barra e quebram o cabecalho.
 */
function ChipsDeJogo() {
  const jogos = useJogosDisponiveis();
  const { jogo: atual, definirJogo } = useJogoAtual();

  if (!jogos.data) return null;

  return (
    <div
      className="rolagem-discreta flex max-w-full items-center gap-space-xs overflow-x-auto"
      role="group"
      aria-label="Jogo do domínio de partidas"
    >
      {jogos.data.map((jogo) => {
        const vazio =
          jogo.partidas === 0 && jogo.equipes === 0 && jogo.agenda === 0;
        const ativo = jogo.codigo === atual;
        const oQueTem = [
          jogo.partidas ? `${jogo.partidas} partidas` : null,
          jogo.equipes ? `${jogo.equipes} equipes` : null,
          jogo.agenda ? `${jogo.agenda} na agenda` : null,
        ]
          .filter(Boolean)
          .join(" · ");

        return (
          <button
            key={jogo.codigo}
            type="button"
            // `shrink-0`: sem isso os chips se espremem ate o nome virar
            // "Counter-..." em vez de rolar.
            data-jogo={jogo.codigo}
            disabled={vazio}
            aria-pressed={ativo}
            onClick={() => definirJogo(jogo.codigo)}
            title={vazio ? "Nada coletado ainda" : oQueTem}
            className={[
              "inline-flex shrink-0 items-center gap-space-xs whitespace-nowrap rounded px-space-md py-space-xs font-title-code text-title-code transition-colors",
              vazio
                ? "cursor-not-allowed bg-surface-container/40 text-outline/50"
                : ativo
                  ? "bg-surface-container-high text-on-surface"
                  : "bg-surface-container text-on-surface-variant hover:text-on-surface",
            ].join(" ")}
          >
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ background: vazio ? "currentColor" : corDoJogo(jogo.codigo) }}
              aria-hidden
            />
            {jogo.nome}
          </button>
        );
      })}
    </div>
  );
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

      <div className="flex items-center gap-space-base">
        <ChipsDeJogo />

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
      </div>
    </header>
  );
}
