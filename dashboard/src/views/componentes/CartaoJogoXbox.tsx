/**
 * Um jogo do catálogo Xbox como cartão — a forma alternativa da tabela.
 *
 * No celular a tabela de 6 colunas espreme; o cartão empilha os mesmos dados
 * (capa, nota, preço, Game Pass) num bloco que lê de relance. Grade
 * `sm:grid-cols-2 xl:grid-cols-3` na tela que o usa.
 */

import { useNavigate } from "react-router-dom";

import type { JogoXbox } from "@models/api/tipos";
import { CapaXbox } from "@views/componentes/CapaXbox";
import { Icone } from "@views/componentes/base";
import { PALETA_POLOS, TOKENS, corDoGenero } from "@views/tema";
import { fmtDecimal, fmtMoeda, fmtNumero, paraNumero } from "@util/formatos";

/** Verde de 4 pra cima, âmbar no meio, apagado abaixo de 3. */
function corDaNota(nota: number): string {
  if (nota >= 4) return PALETA_POLOS.positivo;
  if (nota >= 3) return TOKENS.secundaria;
  return TOKENS.textoSuave;
}

export function CartaoJogoXbox({ jogo }: { jogo: JogoXbox }) {
  const navegar = useNavigate();
  const nota = paraNumero(jogo.nota);

  function abrir() {
    navegar(`/xbox/${jogo.product_id}`);
  }

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={abrir}
      onKeyDown={(evento) => {
        if (evento.key === "Enter" || evento.key === " ") {
          evento.preventDefault();
          abrir();
        }
      }}
      className="flex cursor-pointer flex-col gap-space-sm rounded-xl border border-outline-variant/15 bg-surface-container-low p-space-base transition-colors hover:bg-surface-container-high/60"
    >
      <div className="flex items-start gap-space-sm">
        <CapaXbox
          nome={jogo.nome}
          imagemUrl={jogo.imagem_capa ?? jogo.imagem_header}
          className="h-16 w-16 rounded-lg"
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-headline-sm text-headline-sm font-bold text-primary">
            {jogo.nome}
          </span>
          <span className="truncate font-title-code text-title-code text-outline">
            {jogo.publicadora ?? jogo.desenvolvedora ?? "—"}
          </span>
        </div>
      </div>

      {jogo.generos.length > 0 && (
        <div className="flex flex-wrap gap-space-xxs">
          {jogo.generos.slice(0, 3).map((g) => (
            <span
              key={g}
              className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase"
              style={{ color: corDoGenero(g) }}
            >
              {g}
            </span>
          ))}
          {jogo.generos.length > 3 && (
            <span className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status text-outline">
              +{jogo.generos.length - 3}
            </span>
          )}
        </div>
      )}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-space-xs border-t border-outline-variant/15 pt-space-sm">
        <div className="flex items-center gap-space-sm">
          <span className="font-title-code text-title-code font-bold text-primary">
            {fmtMoeda(jogo.preco_no_momento, jogo.moeda)}
          </span>
          {jogo.desconto_percentual ? (
            <span className="rounded bg-tertiary/10 px-space-xs py-space-xxs font-badge-status text-badge-status text-tertiary">
              -{jogo.desconto_percentual}%
            </span>
          ) : null}
        </div>

        <div className="flex items-center gap-space-xs">
          {nota !== null && (
            <span
              className="inline-flex items-center gap-space-xxs font-title-code text-title-code font-bold"
              style={{ color: corDaNota(nota) }}
            >
              <Icone nome="star" className="text-[13px]" />
              {fmtDecimal(nota, 1)}
              {jogo.numero_avaliacoes ? (
                <span className="font-label-caps text-label-caps text-outline">
                  ({fmtNumero(jogo.numero_avaliacoes)})
                </span>
              ) : null}
            </span>
          )}
          {jogo.no_game_pass && (
            <span className="inline-flex items-center gap-space-xxs rounded bg-tertiary/10 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary">
              <Icone nome="check" className="text-[13px]" />
              Game Pass
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
