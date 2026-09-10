/**
 * Aba PlayStation do catalogo - placeholder ate a chave do PlatPrices sair.
 *
 * O tier gratis do PlatPrices (precos, descontos, PS Plus) esta pendente de
 * aprovacao. Sem ele nao da pra montar a vitrine nem testar a integracao
 * contra a API real, entao a aba fica visivel mas honesta sobre o que falta -
 * mesmo padrao do Assistente de IA quando falta a `OPENROUTER_API_KEY`.
 */

import { Painel } from "@views/componentes/hud";

export function PlayStationEmBreve() {
  return (
    <Painel icone="schedule" titulo="PlayStation Store — em breve">
      <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
        A vitrine da PlayStation Store depende da aprovação da chave da API do{" "}
        <a
          href="https://platprices.com"
          target="_blank"
          rel="noreferrer"
          className="text-primary hover:underline"
        >
          PlatPrices
        </a>{" "}
        — preços, descontos e status do PS Plus. Assim que sair, esta aba passa a
        listar o catálogo do jeito que as outras já fazem. O resto do site
        funciona sem isso.
      </p>
    </Painel>
  );
}
