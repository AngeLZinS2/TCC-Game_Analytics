/**
 * Como cada procedência de bloco se apresenta na tela.
 *
 * A tela tratava `fonte` como booleano — era "steam" ou era nosso. Quando
 * entrou o OP.GG, "opgg" caía no ramo do `else` e um dado de terceiro
 * apareceria rotulado como medição nossa. Justamente a confusão que o painel
 * de contexto existe para impedir.
 *
 * Então a regra passa a ser: `banco` é nosso, qualquer outra coisa é externa e
 * se identifica pelo nome. Uma fonte nova que ninguém mapeou aqui ainda
 * aparece como externa — errar para o lado de "isto não é nosso" é o único
 * erro barato dos dois.
 */

import type { TFunction } from "i18next";

export interface DescricaoFonte {
  /** `false` só para o que a plataforma coletou e mediu. */
  interna: boolean;
  icone: string;
  /** Como o bloco se descreve na lista de fontes. */
  rotulo: string;
  /** O chip curto sobre o bloco. Vazio quando é dado nosso. */
  chip: string;
}

export function descreverFonte(fonte: string, t: TFunction): DescricaoFonte {
  const conhecidas: Record<string, DescricaoFonte> = {
    banco: {
      interna: true,
      icone: "database",
      rotulo: t("assistente.fontes.banco.rotulo"),
      chip: t("assistente.fontes.banco.chip"),
    },
    steam: {
      interna: false,
      icone: "storefront",
      rotulo: t("assistente.fontes.steam.rotulo"),
      chip: t("assistente.fontes.steam.chip"),
    },
    opgg: {
      interna: false,
      icone: "leaderboard",
      rotulo: t("assistente.fontes.opgg.rotulo"),
      chip: t("assistente.fontes.opgg.chip"),
    },
    web: {
      interna: false,
      icone: "travel_explore",
      rotulo: t("assistente.fontes.web.rotulo"),
      chip: t("assistente.fontes.web.chip"),
    },
  };

  return (
    conhecidas[fonte] ?? {
      interna: false,
      icone: "public",
      rotulo: t("assistente.fontes.fallbackRotulo", { fonte }),
      chip: fonte,
    }
  );
}
