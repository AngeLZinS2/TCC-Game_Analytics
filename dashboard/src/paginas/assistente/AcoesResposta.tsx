/**
 * O rodape da resposta: util/nao util e o que dá para levar embora.
 *
 * Uma acao do desenho NAO esta aqui: "Ver consulta". O backend nao devolve
 * SQL - o texto-para-SQL foi justamente o que este projeto rejeitou, as
 * consultas sao escritas a mao no Python e nunca sobem para a resposta.
 * Renderizar o botao exigiria inventar a consulta, entao ele nao existe.
 * "Ver dados" abre o contexto real, que e o que de fato foi usado.
 *
 * O polegar tambem nao tem endpoint: fica no historico local, com a forma que
 * um `POST /api/assistente/feedback` receberia no dia em que existir.
 */

import { useState } from "react";

import type { RespostaAssistente } from "../../api/tipos";
import { Icone } from "../../componentes/base";

/** A resposta inteira em Markdown - com o contexto junto, que e o ponto. */
function paraMarkdown(resposta: RespostaAssistente): string {
  const blocos = resposta.blocos
    .map(
      (bloco) =>
        `### ${bloco.titulo}\n_fonte: ${
          bloco.fonte === "steam" ? "loja da Steam, consultada na hora" : "nosso banco"
        }_\n\n\`\`\`\n${bloco.conteudo}\n\`\`\``,
    )
    .join("\n\n");

  return [
    `# ${resposta.pergunta}`,
    "",
    resposta.resposta,
    "",
    `> Gerado por ${resposta.modelo} a partir do contexto abaixo.`,
    "",
    "## Contexto usado",
    "",
    blocos,
    "",
  ].join("\n");
}

export function AcoesResposta({
  resposta,
  util,
  aoAvaliar,
  aoVerDados,
}: {
  resposta: RespostaAssistente;
  util: boolean | null;
  aoAvaliar: (util: boolean | null) => void;
  aoVerDados: () => void;
}) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(resposta.resposta);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      // Sem permissao de area de transferencia: o botao so nao confirma.
      // Nao vale um alerta - o texto continua selecionavel na tela.
    }
  }

  function exportar() {
    const blob = new Blob([paraMarkdown(resposta)], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `assistente-${Date.now()}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-space-base border-t border-outline-variant/20 pt-space-base">
      <div className="flex items-center gap-space-xs">
        <span className="font-body-sm text-body-sm text-outline">
          Essa resposta foi útil?
        </span>
        {[true, false].map((valor) => {
          const ativo = util === valor;
          return (
            <button
              key={String(valor)}
              type="button"
              // Clicar de novo desmarca: quem errou o polegar tem como voltar.
              onClick={() => aoAvaliar(ativo ? null : valor)}
              aria-pressed={ativo}
              aria-label={valor ? "Resposta útil" : "Resposta não útil"}
              title={
                valor ? "Marcar como útil" : "Marcar como não útil"
              }
              className={[
                "rounded p-space-xs transition-colors",
                ativo
                  ? valor
                    ? "bg-tertiary/15 text-tertiary"
                    : "bg-error/15 text-error"
                  : "bg-surface-container text-outline hover:text-on-surface",
              ].join(" ")}
            >
              <Icone nome={valor ? "thumb_up" : "thumb_down"} className="text-[16px]" />
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-space-xs">
        <Acao icone={copiado ? "check" : "content_copy"} rotulo={copiado ? "Copiado" : "Copiar"} aoClicar={copiar} />
        <Acao icone="download" rotulo="Exportar" aoClicar={exportar} />
        <Acao icone="table_rows" rotulo="Ver dados" aoClicar={aoVerDados} />
      </div>
    </div>
  );
}

function Acao({
  icone,
  rotulo,
  aoClicar,
}: {
  icone: string;
  rotulo: string;
  aoClicar: () => void;
}) {
  return (
    <button
      type="button"
      onClick={aoClicar}
      className="flex items-center gap-space-xxs rounded bg-surface-container px-space-sm py-space-xs font-title-code text-title-code text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-primary"
    >
      <Icone nome={icone} className="text-[16px]" />
      {rotulo}
    </button>
  );
}
