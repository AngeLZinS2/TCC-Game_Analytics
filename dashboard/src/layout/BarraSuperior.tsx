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
 * Um jogo sem partida coletada aparece desabilitado em vez de sumir: o schema
 * de partidas ja e compartilhado entre os tres, e mostrar o que ainda nao foi
 * populado e mostrar o plano do projeto na tela.
 */
function ChipsDeJogo() {
  const jogos = useJogosDisponiveis();
  const { jogo: atual, definirJogo } = useJogoAtual();

  if (!jogos.data) return null;

  return (
    <div
      className="flex items-center gap-space-xs"
      role="group"
      aria-label="Jogo do domínio de partidas"
    >
      {jogos.data.map((jogo) => {
        const vazio = jogo.partidas === 0;
        const ativo = jogo.codigo === atual;

        return (
          <button
            key={jogo.codigo}
            type="button"
            disabled={vazio}
            aria-pressed={ativo}
            onClick={() => definirJogo(jogo.codigo)}
            title={vazio ? "Nenhuma partida coletada ainda" : `${jogo.partidas} partidas`}
            className={[
              "inline-flex items-center gap-space-xs rounded px-space-md py-space-xs font-title-code text-title-code transition-colors",
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
