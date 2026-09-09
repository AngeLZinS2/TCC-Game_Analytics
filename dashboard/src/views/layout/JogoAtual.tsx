/**
 * O jogo do dominio de esports, escolhido uma vez e valido em todas as telas.
 *
 * O seletor (`componentes/SeletorDeJogo.tsx`) e o menu da barra
 * (`componentes/MenuEsports.tsx`) trocam o jogo, mas a escolha continua uma so,
 * e nao o estado de uma pagina: e por isso que ela vive aqui, num contexto
 * acima de todas elas. Trocar o jogo na aba Herois e abrir Jogadores em
 * seguida tem que manter a escolha.
 *
 * **De onde vem o valor depende de onde voce esta.** Dentro da aba E-Sports o
 * jogo e o primeiro segmento da rota (`/esports/:jogo/:aba`) - assim um link
 * para "Ranking do LoL" continua sendo isso quando alguem cola o endereco, e o
 * botao de voltar desfaz a troca. Fora dela (telas de detalhe que ainda usam
 * `?jogo=`, ou um link legado) cai no parametro de busca, e por fim no padrao.
 */

import { createContext, useCallback, useContext, type ReactNode } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

/** O star schema nasceu com Dota 2; e o unico com partida detalhada. */
const PADRAO = "dota2";

/** `/esports/<jogo>/<aba>` - captura o jogo e a aba atual. */
const ROTA_ESPORTS = /^\/esports\/([^/]+)(?:\/([^/]+))?/;

/** A aba que um link para `/esports/<jogo>` sem aba deve abrir. */
const ABA_PADRAO = "partidas";

interface ContextoJogo {
  jogo: string;
  definirJogo: (codigo: string) => void;
}

const Contexto = createContext<ContextoJogo | null>(null);

export function ProvedorJogo({ children }: { children: ReactNode }) {
  const [parametros, definirParametros] = useSearchParams();
  const { pathname } = useLocation();
  const navegar = useNavigate();

  const casaEsports = pathname.match(ROTA_ESPORTS);
  const jogo = casaEsports?.[1] ?? parametros.get("jogo") ?? PADRAO;

  const definirJogo = useCallback(
    (codigo: string) => {
      const casa = pathname.match(ROTA_ESPORTS);
      if (casa) {
        // Dentro da aba E-Sports: o jogo e a rota. Mantem a sub-aba atual e
        // descarta a query (um `?a=` de time e especifico do jogo anterior).
        const aba = casa[2] ?? ABA_PADRAO;
        navegar(`/esports/${codigo}/${aba}`, { replace: true });
        return;
      }
      definirParametros(
        (anteriores) => {
          const proximos = new URLSearchParams(anteriores);
          if (codigo === PADRAO) proximos.delete("jogo");
          else proximos.set("jogo", codigo);
          return proximos;
        },
        { replace: true },
      );
    },
    [pathname, navegar, definirParametros],
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
