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

export interface DescricaoFonte {
  /** `false` só para o que a plataforma coletou e mediu. */
  interna: boolean;
  icone: string;
  /** Como o bloco se descreve na lista de fontes. */
  rotulo: string;
  /** O chip curto sobre o bloco. Vazio quando é dado nosso. */
  chip: string;
}

const CONHECIDAS: Record<string, DescricaoFonte> = {
  banco: { interna: true, icone: "database", rotulo: "nosso banco", chip: "" },
  steam: {
    interna: false,
    icone: "storefront",
    rotulo: "loja da Steam, agora",
    chip: "fora do banco",
  },
  opgg: {
    interna: false,
    icone: "leaderboard",
    rotulo: "OP.GG, agora",
    chip: "OP.GG",
  },
};

export function descreverFonte(fonte: string): DescricaoFonte {
  return (
    CONHECIDAS[fonte] ?? {
      interna: false,
      icone: "public",
      rotulo: `${fonte}, agora`,
      chip: fonte,
    }
  );
}
