/**
 * "Como chegamos nessa resposta?" - o caminho real, com os nomes reais.
 *
 * Cada etapa aqui e um fato que a resposta carrega: os blocos que o backend
 * escolheu (`resposta.blocos`, com titulo e fonte), o tamanho do contexto em
 * linhas e tokens, o modelo que redigiu. Nao ha etapa generica de enfeite -
 * o desenho sugeria "filtramos ultimos 30 dias" e "ordenamos por winrate
 * DESC", e essas frases so poderiam existir aqui inventadas, porque o backend
 * nao devolve o SQL nem o filtro que usou.
 */

import { useState } from "react";

import type { RespostaAssistente } from "../../api/tipos";
import { Icone } from "../../componentes/base";
import { fmtNumero } from "../../utilitarios/formatos";

interface Etapa {
  titulo: string;
  detalhe: string;
  icone: string;
}

function etapasDe(resposta: RespostaAssistente): Etapa[] {
  const linhas = resposta.blocos.reduce(
    (soma, bloco) => soma + bloco.conteudo.split("\n").length,
    0,
  );
  const daLoja = resposta.blocos.filter((b) => b.fonte === "steam");

  const etapas: Etapa[] = [
    {
      titulo: "Lemos a pergunta",
      detalhe: resposta.pergunta,
      icone: "help",
    },
    {
      titulo: `Escolhemos ${resposta.blocos.length} ${
        resposta.blocos.length === 1 ? "bloco" : "blocos"
      }`,
      detalhe: resposta.blocos.map((b) => b.titulo).join(" · "),
      icone: "checklist",
    },
    {
      titulo: "Consultamos o banco",
      detalhe: `${fmtNumero(linhas)} linhas de contexto, por SQL escrito à mão`,
      icone: "database",
    },
  ];

  // So aparece quando aconteceu de verdade - a busca ao vivo na loja e
  // condicional (a pergunta precisa citar um jogo).
  if (daLoja.length > 0) {
    etapas.push({
      titulo: "Consultamos a loja agora",
      detalhe: daLoja.map((b) => b.titulo).join(" · "),
      icone: "storefront",
    });
  }

  etapas.push(
    {
      titulo: "O modelo redigiu",
      detalhe: `${resposta.modelo}${
        resposta.tokens_entrada
          ? ` · ${fmtNumero(resposta.tokens_entrada)} tokens de contexto`
          : ""
      }`,
      icone: "smart_toy",
    },
    {
      titulo: "Devolvemos o contexto junto",
      detalhe: "todo número da resposta pode ser conferido aqui na tela",
      icone: "fact_check",
    },
  );

  return etapas;
}

export function ComoChegamos({ resposta }: { resposta: RespostaAssistente }) {
  const [aberto, setAberto] = useState(false);
  const etapas = etapasDe(resposta);

  return (
    <div className="rounded-xl bg-surface-container-low/90 shadow-2xl">
      <button
        type="button"
        onClick={() => setAberto((atual) => !atual)}
        aria-expanded={aberto}
        className="flex w-full items-center justify-between gap-space-sm rounded-xl px-space-lg py-space-base text-left transition-colors hover:bg-surface-container/40"
      >
        <span className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-primary">
          <Icone nome="account_tree" className="text-[16px]" />
          Como chegamos nessa resposta?
        </span>
        <Icone
          nome={aberto ? "expand_less" : "expand_more"}
          className="text-[20px] text-outline"
        />
      </button>

      {aberto && (
        <ol className="flex flex-col gap-space-xs px-space-lg pb-space-lg md:flex-row md:flex-wrap">
          {etapas.map((etapa, indice) => (
            <li
              key={etapa.titulo}
              className="flex min-w-0 flex-1 items-start gap-space-sm rounded-lg bg-surface-container-lowest p-space-sm md:min-w-[180px]"
            >
              <span
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary-container/15 font-badge-status text-badge-status text-primary ring-1 ring-primary/30"
                aria-hidden
              >
                {indice + 1}
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-space-xxs font-title-code text-title-code text-on-surface">
                  <Icone nome={etapa.icone} className="text-[14px] text-outline" />
                  {etapa.titulo}
                </div>
                <p className="mt-space-xxs break-words font-body-sm text-body-sm text-outline">
                  {etapa.detalhe}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
