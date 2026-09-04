/**
 * Escolha do jogo do domínio de partidas, revelada ao passar o mouse.
 *
 * Morava fixo na barra superior — e isso parou de fazer sentido quando o
 * catálogo passou de 3 jogos para dezenas com dado real: os chips quebravam o
 * cabeçalho, ou precisavam rolar por cima dele em toda tela, mesmo nas que
 * não usam jogo nenhum (Visão Geral, Assistente de IA). Agora o seletor mora
 * só nas telas que de fato dependem do jogo, e só ocupa espaço quando alguém
 * pede: um botão mostra o jogo atual, e passar o mouse — ou clicar, para quem
 * navega por teclado ou toque — revela a lista.
 *
 * **O vão entre o botão e o painel é preenchido, não pulado.** O painel abre
 * num `div` que começa exatamente em `top-full` (sem margem) e usa padding
 * para o respiro visual, não `margin` — porque `mouseleave` do envoltório só
 * dispara quando o ponteiro sai da sua subárvore, e uma margem criaria um
 * vão sem dono entre o botão e a lista: a causa mais comum de um menu por
 * hover "fechar sozinho" ao descer até ele.
 */

import { useEffect, useRef, useState } from "react";

import { useJogosDisponiveis } from "../api/consultas";
import type { JogoDisponivel } from "../api/tipos";
import { useJogoAtual } from "../layout/JogoAtual";
import { corDoJogo } from "../tema";
import { Icone } from "./base";

/** O que a linha de um jogo indisponível mostra em vez da contagem. */
const SEM_DADO = "Nada coletado ainda";

function oQueTem(jogo: JogoDisponivel): string {
  return [
    jogo.partidas ? `${jogo.partidas} partidas` : null,
    jogo.equipes ? `${jogo.equipes} equipes` : null,
    jogo.agenda ? `${jogo.agenda} na agenda` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function SeletorDeJogo({
  disponivel = (jogo) => jogo.partidas > 0,
}: {
  /**
   * Quando um jogo do catálogo pode ser escolhido nesta tela.
   *
   * O padrão exige partida coletada — vale para Partidas, Heróis e
   * Jogadores, que leem o fato de partida. A Previsão de Confronto passa um
   * critério mais largo: a agenda (Liquipedia) de um jogo pode existir antes
   * de qualquer confronto decidido dele ter entrado no banco.
   */
  disponivel?: (jogo: JogoDisponivel) => boolean;
}) {
  const jogos = useJogosDisponiveis();
  const { jogo: atual, definirJogo } = useJogoAtual();
  const [aberto, setAberto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);

  // Clique fora fecha. Sem isso, quem abriu por clique (toque, teclado) so
  // fecharia levando o mouse embora e trazendo de volta - o gesto errado.
  useEffect(() => {
    if (!aberto) return;

    function aoClicarFora(evento: MouseEvent) {
      if (!raiz.current?.contains(evento.target as Node)) setAberto(false);
    }
    function aoTeclarEscape(evento: KeyboardEvent) {
      if (evento.key === "Escape") setAberto(false);
    }

    document.addEventListener("mousedown", aoClicarFora);
    document.addEventListener("keydown", aoTeclarEscape);
    return () => {
      document.removeEventListener("mousedown", aoClicarFora);
      document.removeEventListener("keydown", aoTeclarEscape);
    };
  }, [aberto]);

  if (!jogos.data) return null;

  const atualDados = jogos.data.find((j) => j.codigo === atual);

  return (
    <div
      ref={raiz}
      className="relative"
      onMouseEnter={() => setAberto(true)}
      onMouseLeave={() => setAberto(false)}
    >
      <button
        type="button"
        onClick={() => setAberto((estava) => !estava)}
        aria-haspopup="listbox"
        aria-expanded={aberto}
        className="flex items-center gap-space-xs rounded bg-surface-container px-space-md py-space-xs font-title-code text-title-code text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface"
      >
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ background: corDoJogo(atual) }}
          aria-hidden
        />
        {atualDados?.nome ?? atual}
        <Icone
          nome="expand_more"
          className={`text-[16px] text-outline transition-transform ${
            aberto ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* O padding-top e o "vao preenchido" do comentario acima: comeca em
          top-full (sem gap) e da o respiro visual por dentro da propria area
          hoveravel, nao por fora dela. */}
      {aberto && (
        <div className="absolute left-0 top-full z-30 w-max pt-space-xs">
          <div
            role="listbox"
            aria-label="Selecionar jogo"
            className="rolagem-discreta flex max-h-80 min-w-52 flex-col gap-space-xxs overflow-y-auto rounded-lg border border-outline-variant/30 bg-surface-container-low p-space-xs shadow-2xl"
          >
            {jogos.data.map((jogo) => {
              const podeEscolher = disponivel(jogo);
              const ativo = jogo.codigo === atual;

              return (
                <button
                  key={jogo.codigo}
                  type="button"
                  role="option"
                  aria-selected={ativo}
                  disabled={!podeEscolher}
                  onClick={() => {
                    definirJogo(jogo.codigo);
                    setAberto(false);
                  }}
                  className={[
                    "flex flex-col items-start gap-0.5 rounded px-space-sm py-space-xs text-left transition-colors",
                    !podeEscolher
                      ? "cursor-not-allowed opacity-50"
                      : ativo
                        ? "bg-surface-container-high"
                        : "hover:bg-surface-container-high",
                  ].join(" ")}
                >
                  <span className="flex items-center gap-space-xs font-title-code text-title-code text-on-surface">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: corDoJogo(jogo.codigo) }}
                      aria-hidden
                    />
                    <span className="truncate">{jogo.nome}</span>
                  </span>
                  <span className="pl-[16px] font-label-caps text-label-caps text-outline">
                    {podeEscolher ? oQueTem(jogo) : SEM_DADO}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
