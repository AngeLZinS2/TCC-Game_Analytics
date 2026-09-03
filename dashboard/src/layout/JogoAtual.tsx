/**
 * O jogo do dominio de partidas, escolhido uma vez e valido em todas as telas.
 *
 * No desenho do Stitch os chips de jogo ficam na barra superior, acima das
 * telas - entao a escolha nao pode morar no estado de uma pagina. Ela vive
 * aqui, e Partidas, Herois e Jogadores leem daqui.
 *
 * O valor fica na URL (`?jogo=`) e nao em estado local: assim um link para
 * "Herois do LoL" continua sendo um link para os herois do LoL quando alguem
 * cola o endereco, e o botao de voltar do navegador desfaz a troca de jogo.
 */

import { createContext, useCallback, useContext, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

/** O star schema nasceu com Dota 2; e o unico com dados na Fase 2. */
const PADRAO = "dota2";

interface ContextoJogo {
  jogo: string;
  definirJogo: (codigo: string) => void;
}

const Contexto = createContext<ContextoJogo | null>(null);

export function ProvedorJogo({ children }: { children: ReactNode }) {
  const [parametros, definirParametros] = useSearchParams();
  const jogo = parametros.get("jogo") ?? PADRAO;

  const definirJogo = useCallback(
    (codigo: string) => {
      definirParametros(
        (anteriores) => {
          const proximos = new URLSearchParams(anteriores);
          // O padrao nao precisa aparecer na URL; so o desvio dele.
          if (codigo === PADRAO) proximos.delete("jogo");
          else proximos.set("jogo", codigo);
          return proximos;
        },
        { replace: true },
      );
    },
    [definirParametros],
  );

  return (
    <Contexto.Provider value={{ jogo, definirJogo }}>{children}</Contexto.Provider>
  );
}

export function useJogoAtual(): ContextoJogo {
  const contexto = useContext(Contexto);
  if (!contexto) throw new Error("useJogoAtual precisa estar dentro do ProvedorJogo");
  return contexto;
}
