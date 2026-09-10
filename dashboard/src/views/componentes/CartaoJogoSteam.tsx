/**
 * Uma linha do catálogo Steam como cartão — a forma alternativa da tabela de
 * 8 colunas (que espreme no celular).
 *
 * Serve as duas procedências do `LinhaCatalogo`: `coletado` (com telemetria)
 * e `loja` (jogo achado na busca, ainda sem coleta — células de telemetria
 * viram travessão, igual `LinhaDaLoja` na tabela). O clique dispara o
 * `aoClicar` da tela, porque o fluxo "coleta e abre" mora lá.
 */

import type { LinhaCatalogo } from "@models/api/tipos";
import { CapaJogo } from "@views/componentes/CapaJogo";
import { Icone } from "@views/componentes/base";
import { corDoGenero } from "@views/tema";
import {
  classificacaoSteam,
  fmtCurto,
  fmtMoeda,
  fmtNumero,
  fmtPercentual,
} from "@util/formatos";

const CHIP_CLASSIFICACAO = {
  positiva: "bg-tertiary/10 text-tertiary",
  neutra: "bg-surface-container-highest text-on-surface-variant",
  negativa: "bg-error/10 text-error",
} as const;

export function CartaoJogoSteam({
  linha,
  aoClicar,
  carregando = false,
}: {
  linha: LinhaCatalogo;
  aoClicar: () => void;
  carregando?: boolean;
}) {
  const daLoja = linha.tipo === "loja";
  const nome = daLoja ? linha.candidato.nome : linha.jogo.nome;
  const appId = daLoja ? linha.candidato.app_id : linha.jogo.app_id;
  const imagem = daLoja ? linha.candidato.imagem : linha.jogo.imagem_header;
  const generos = daLoja ? [] : linha.jogo.generos;

  const classificacao = daLoja
    ? null
    : classificacaoSteam(linha.jogo.classificacao_steam);

  return (
    <article
      role="button"
      tabIndex={carregando ? -1 : 0}
      aria-busy={carregando}
      onClick={carregando ? undefined : aoClicar}
      onKeyDown={(evento) => {
        if (!carregando && (evento.key === "Enter" || evento.key === " ")) {
          evento.preventDefault();
          aoClicar();
        }
      }}
      className={`flex flex-col gap-space-sm rounded-xl border border-outline-variant/15 bg-surface-container-low p-space-base transition-colors ${
        carregando
          ? "cursor-progress bg-surface-container-high/40"
          : "cursor-pointer hover:bg-surface-container-high/60"
      }`}
    >
      <div className="flex items-start gap-space-sm">
        <CapaJogo
          appId={appId}
          nome={nome}
          imagemUrl={imagem}
          className="h-16 w-16 rounded-lg"
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="flex items-center gap-space-xs">
            <span className="truncate font-headline-sm text-headline-sm font-bold text-primary">
              {nome}
            </span>
            {daLoja && (
              <span className="shrink-0 rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-outline">
                da loja
              </span>
            )}
          </span>
          <span className="font-title-code text-title-code text-outline">
            AppID <span className="font-bold text-on-surface-variant">{appId}</span>
            {!daLoja && linha.jogo.desenvolvedora ? ` · ${linha.jogo.desenvolvedora}` : ""}
          </span>
        </div>
      </div>

      {generos.length > 0 && (
        <div className="flex flex-wrap gap-space-xxs">
          {generos.slice(0, 3).map((g) => (
            <span
              key={g}
              className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status uppercase"
              style={{ color: corDoGenero(g) }}
            >
              {g}
            </span>
          ))}
          {generos.length > 3 && (
            <span className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status text-outline">
              +{generos.length - 3}
            </span>
          )}
        </div>
      )}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-space-xs border-t border-outline-variant/15 pt-space-sm">
        {daLoja ? (
          <span className="font-title-code text-title-code text-outline">
            {carregando ? "buscando dados…" : "sem coleta"}
          </span>
        ) : (
          <div className="flex items-center gap-space-md">
            <span className="flex flex-col leading-tight">
              <span className="font-headline-sm text-headline-sm font-bold text-tertiary">
                {fmtNumero(linha.jogo.jogadores_simultaneos)}
              </span>
              <span className="font-label-caps text-label-caps text-outline">jogando</span>
            </span>
            <span className="font-title-code text-title-code text-on-surface-variant">
              {fmtPercentual(linha.jogo.nota_avaliacoes, 0)}{" "}
              <span className="text-outline">({fmtCurto(linha.jogo.numero_avaliacoes)})</span>
            </span>
            {classificacao && (
              <span
                className={`rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase ${
                  CHIP_CLASSIFICACAO[classificacao.polaridade]
                }`}
              >
                {classificacao.texto}
              </span>
            )}
          </div>
        )}

        <div className="flex items-center gap-space-xs">
          <span className="font-title-code text-title-code font-bold text-primary">
            {daLoja
              ? linha.candidato.preco_centavos === null ||
                linha.candidato.preco_centavos === undefined
                ? "—"
                : fmtMoeda(
                    linha.candidato.preco_centavos / 100,
                    linha.candidato.moeda ?? undefined,
                  )
              : fmtMoeda(linha.jogo.preco_no_momento, linha.jogo.moeda)}
          </span>
          {!daLoja && linha.jogo.desconto_percentual ? (
            <span className="rounded bg-tertiary/10 px-space-xs py-space-xxs font-badge-status text-badge-status text-tertiary">
              -{linha.jogo.desconto_percentual}%
            </span>
          ) : null}
          {carregando && (
            <Icone nome="progress_activity" className="animate-spin text-[16px] text-primary" />
          )}
        </div>
      </div>
    </article>
  );
}
