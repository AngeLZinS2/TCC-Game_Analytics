/**
 * Confrontos já decididos: quem jogou, o placar da série e onde.
 *
 * O grão é declarado de propósito no cabeçalho do painel que usa isto: aqui é
 * "quem venceu a série", não "o que aconteceu dentro dela". Um 3x1 é uma linha,
 * não três partidas — misturar os dois grãos na mesma contagem seria inflar o
 * volume coletado com uma conversão que ninguém fez.
 *
 * O escudo só aparece quando a equipe foi reconciliada com a dimensão. Nos
 * jogos da Liquipedia isso quase nunca acontece (ela escreve o nome, não o id),
 * então a sigla e o nome carregam a identificação sozinhos — e a linha continua
 * legível sem imagem nenhuma, em vez de abrir um buraco.
 */

import type { ConfrontoResultado } from "../api/tipos";
import { fmtDataHora } from "../utilitarios/formatos";

/** O lado de um confronto: escudo, nome e placar, com o vencedor em destaque. */
function Lado({
  nome,
  logo,
  tag,
  placar,
  venceu,
  alinharDireita = false,
}: {
  nome: string;
  logo: string | null;
  tag: string | null;
  placar: number | null;
  venceu: boolean;
  alinharDireita?: boolean;
}) {
  return (
    <div
      className={`flex min-w-0 flex-1 items-center gap-space-sm ${
        alinharDireita ? "flex-row-reverse text-right" : ""
      }`}
    >
      {logo ? (
        // Placa clara atrás do escudo. Medindo os crests do OP.GG, a
        // luminância média vai de 0 (Dplus KIA é preto puro) a 173, com a
        // maioria entre 70 e 90: sobre o fundo escuro do HUD eles carregavam,
        // ocupavam os 28px e simplesmente não se viam. Escudo de esports é
        // desenhado para fundo branco — é para lá que a placa os leva, em vez
        // de a tela apostar que cada um trouxe contraste próprio.
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-neutral-200 p-[3px]">
          <img src={logo} alt="" loading="lazy" className="max-h-full max-w-full object-contain" />
        </span>
      ) : (
        <span
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-surface-container-highest font-badge-status text-badge-status uppercase text-outline"
          aria-hidden
        >
          {(tag || nome).slice(0, 3)}
        </span>
      )}
      <span
        className={`truncate font-title-code text-title-code ${
          venceu ? "text-on-surface" : "text-outline"
        }`}
        title={nome}
      >
        {nome}
      </span>
      <span
        className={`shrink-0 font-headline-sm text-headline-sm tabular-nums ${
          venceu ? "text-primary" : "text-outline"
        }`}
      >
        {placar ?? "-"}
      </span>
    </div>
  );
}

export function ListaConfrontos({ confrontos }: { confrontos: ConfrontoResultado[] }) {
  return (
    <ul className="flex flex-col gap-space-xs">
      {confrontos.map((c) => (
        <li
          key={c.id_externo}
          className="flex flex-col gap-space-xs rounded-lg bg-surface-container-lowest p-space-sm"
        >
          <div className="flex items-center gap-space-sm">
            <Lado
              nome={c.equipe_a_nome}
              logo={c.equipe_a_logo}
              tag={c.equipe_a_tag}
              placar={c.placar_a}
              venceu={c.vitoria_a === true}
            />
            <span className="shrink-0 font-badge-status text-badge-status uppercase text-outline">
              vs
            </span>
            <Lado
              nome={c.equipe_b_nome}
              logo={c.equipe_b_logo}
              tag={c.equipe_b_tag}
              placar={c.placar_b}
              venceu={c.vitoria_a === false}
              alinharDireita
            />
          </div>

          <div className="flex flex-wrap items-center gap-space-xs border-t border-outline-variant/20 pt-space-xs font-badge-status text-badge-status uppercase tracking-wider text-outline">
            {c.torneio && (
              <span className="min-w-0 truncate" title={c.torneio}>
                {c.torneio}
              </span>
            )}
            {c.formato && <span className="shrink-0">· {c.formato}</span>}
            <span className="ml-auto shrink-0 tabular-nums">
              {fmtDataHora(c.inicio_previsto)}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
