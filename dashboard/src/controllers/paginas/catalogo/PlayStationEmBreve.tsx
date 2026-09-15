/**
 * Aba PlayStation do catalogo - placeholder ate a chave do PlatPrices sair.
 *
 * O tier gratis do PlatPrices (precos, descontos, PS Plus) esta pendente de
 * aprovacao. Sem ele nao da pra montar a vitrine nem testar a integracao
 * contra a API real, entao a aba fica visivel mas honesta sobre o que falta -
 * mesmo padrao do Assistente de IA quando falta a `OPENROUTER_API_KEY`.
 */

import { useTranslation } from "react-i18next";

import { Painel } from "@views/componentes/hud";

export function PlayStationEmBreve() {
  const { t } = useTranslation();
  return (
    <Painel icone="schedule" titulo={t("catalogoPlayStation.titulo")}>
      <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
        {t("catalogoPlayStation.descricaoPrefixo")}
        <a
          href="https://platprices.com"
          target="_blank"
          rel="noreferrer"
          className="text-primary hover:underline"
        >
          PlatPrices
        </a>
        {t("catalogoPlayStation.descricaoSufixo")}
      </p>
    </Painel>
  );
}
