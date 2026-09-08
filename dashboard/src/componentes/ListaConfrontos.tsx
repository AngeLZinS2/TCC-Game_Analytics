/**
 * Confrontos já decididos, no estilo de placar de esports (HLTV/vlr.gg):
 * o duelo fica junto e centrado — `Time A  escudo  2 – 0  escudo  Time B` — com
 * o placar em destaque (verde quem venceu, vermelho quem perdeu) e a coluna do
 * placar alinhada verticalmente entre as linhas, para varrer a lista de cima a
 * baixo. Depois vem o torneio e, à direita, o formato e quando foi.
 *
 * O grão é "quem venceu a série", não "o que aconteceu dentro dela": um 3x1 é
 * uma linha. Clicar numa linha com `tem_detalhe` abre o placar por mapa.
 *
 * O escudo só aparece quando a equipe foi reconciliada com a dimensão — nos
 * jogos da Liquipedia isso quase nunca acontece, então a sigla segura a
 * identificação e a linha continua legível sem imagem.
 */

import { useState } from "react";

import type { ConfrontoResultado } from "../api/tipos";
import { PALETA_POLOS } from "../tema";
import { fmtRelativo } from "../utilitarios/formatos";
import { ModalConfrontoDetalhe } from "./ModalConfrontoDetalhe";
import { Icone } from "./base";

function Escudo({
  logo,
  tag,
  nome,
}: {
  logo: string | null;
  tag: string | null;
  nome: string;
}) {
  if (logo) {
    // Placa clara atrás do escudo: crest de esports é desenhado para fundo
    // branco e some sobre o HUD escuro se a tela apostar no contraste dele.
    return (
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm bg-neutral-200 p-[3px]">
        <img
          src={logo}
          alt=""
          loading="lazy"
          className="max-h-full max-w-full object-contain"
        />
      </span>
    );
  }
  return (
    <span
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm bg-surface-container-highest text-[9px] font-bold uppercase leading-none text-outline"
      aria-hidden
    >
      {(tag || nome).slice(0, 2)}
    </span>
  );
}

function Placar({
  valor,
  venceu,
  semResultado,
}: {
  valor: number | null;
  venceu: boolean;
  semResultado: boolean;
}) {
  const cor = semResultado
    ? undefined
    : venceu
      ? PALETA_POLOS.positivo
      : PALETA_POLOS.negativo;
  return (
    <span
      className="w-[1.1rem] text-center font-headline-sm text-headline-sm tabular-nums"
      style={{ color: cor }}
    >
      {valor ?? "–"}
    </span>
  );
}

export function ListaConfrontos({ confrontos }: { confrontos: ConfrontoResultado[] }) {
  // `id_externo` do confronto cujo detalhe por mapa está aberto no modal.
  const [aberto, setAberto] = useState<string | null>(null);

  return (
    <>
      <ul className="divide-y divide-outline-variant/10 overflow-hidden rounded-lg bg-surface-container-lowest">
        {confrontos.map((c, indice) => {
          const semResultado = c.vitoria_a === null && c.placar_a === null;
          const nomeA = `truncate font-title-code text-title-code ${
            c.vitoria_a === true
              ? "font-bold text-on-surface"
              : "text-on-surface-variant"
          }`;
          const nomeB = `truncate font-title-code text-title-code ${
            c.vitoria_a === false
              ? "font-bold text-on-surface"
              : "text-on-surface-variant"
          }`;

          return (
            <li
              key={c.id_externo}
              onClick={c.tem_detalhe ? () => setAberto(c.id_externo) : undefined}
              className={[
                "flex flex-col gap-space-xxs px-space-sm py-space-xs sm:flex-row sm:items-center sm:gap-space-md",
                indice % 2 ? "bg-white/[0.015]" : "",
                c.tem_detalhe
                  ? "cursor-pointer transition-colors hover:bg-surface-container-high/50"
                  : "",
              ].join(" ")}
            >
              {/* ---------- O duelo, junto e com o placar alinhado ---------- */}
              <div className="flex shrink-0 items-center gap-space-xs sm:w-[23rem] lg:w-[28rem]">
                <span className={`min-w-0 flex-1 text-right ${nomeA}`} title={c.equipe_a_nome}>
                  {c.equipe_a_nome}
                </span>
                <Escudo logo={c.equipe_a_logo} tag={c.equipe_a_tag} nome={c.equipe_a_nome} />

                <span className="flex shrink-0 items-center gap-0.5">
                  <Placar
                    valor={c.placar_a}
                    venceu={c.vitoria_a === true}
                    semResultado={semResultado}
                  />
                  <span className="text-outline">-</span>
                  <Placar
                    valor={c.placar_b}
                    venceu={c.vitoria_a === false}
                    semResultado={semResultado}
                  />
                </span>

                <Escudo logo={c.equipe_b_logo} tag={c.equipe_b_tag} nome={c.equipe_b_nome} />
                <span className={`min-w-0 flex-1 text-left ${nomeB}`} title={c.equipe_b_nome}>
                  {c.equipe_b_nome}
                </span>
              </div>

              {/* ---------- Torneio ---------- */}
              <div className="flex min-w-0 flex-1 items-center gap-space-xs font-body-sm text-body-sm text-outline">
                <Icone
                  nome="emoji_events"
                  className="hidden shrink-0 text-[14px] sm:inline"
                />
                <span className="truncate" title={c.torneio ?? undefined}>
                  {c.torneio ?? "—"}
                </span>
              </div>

              {/* ---------- Formato + quando ---------- */}
              <div className="flex shrink-0 items-center gap-space-sm font-badge-status text-badge-status uppercase tracking-wider text-outline">
                {c.tem_detalhe && (
                  <Icone
                    nome="scoreboard"
                    className="shrink-0 text-[14px] text-primary"
                    // O único ponto onde stats por mapa existem hoje.
                  />
                )}
                {c.formato && (
                  <span className="rounded bg-surface-container px-space-xxs py-[1px] text-on-surface-variant">
                    {c.formato}
                  </span>
                )}
                <span className="tabular-nums">{fmtRelativo(c.inicio_previsto)}</span>
              </div>
            </li>
          );
        })}
      </ul>

      <ModalConfrontoDetalhe idExterno={aberto} aoFechar={() => setAberto(null)} />
    </>
  );
}
