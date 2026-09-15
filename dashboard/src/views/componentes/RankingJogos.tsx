/**
 * "Top jogos por jogadores simultâneos" — o ranking em linhas do catálogo.
 *
 * Substitui as barras de gradiente que existiam antes: a barra comunicava
 * proporção, mas escondia o que a pessoa vem buscar aqui (qual jogo, de que
 * gênero, subindo ou caindo, com que curva). Cada linha traz capa, gênero,
 * contagem, variação e a série recente — tudo dado real; a série vem em lote
 * de `GET /api/steam/series-jogadores`, uma chamada para o ranking inteiro.
 *
 * Duas colunas no desktop (1-5 / 6-10) e uma só no celular, como o resto do
 * dashboard faz com grades densas.
 */

import { useTranslation } from "react-i18next";

import { CapaJogo } from "@views/componentes/CapaJogo";
import { Icone } from "@views/componentes/base";
import { Sparkline } from "@views/componentes/hud";
import { corDoGenero } from "@views/tema";
import { fmtNumero, fmtPercentual } from "@util/formatos";

export interface ItemRanking {
  app_id: number;
  nome: string;
  imagem_header: string | null;
  generos: string[];
  jogadores_simultaneos: number | null;
  /** Variação sobre a coleta anterior. `null` = ainda sem com o que comparar. */
  variacao: number | null;
  /** Série recente; vazia quando ainda não há histórico do jogo. */
  serie: number[];
}

function LinhaRanking({
  item,
  posicao,
  aoClicar,
}: {
  item: ItemRanking;
  posicao: number;
  aoClicar: () => void;
}) {
  const { t } = useTranslation();
  const subiu = (item.variacao ?? 0) >= 0;

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={aoClicar}
      onKeyDown={(evento) => {
        if (evento.key === "Enter" || evento.key === " ") {
          evento.preventDefault();
          aoClicar();
        }
      }}
      className="flex cursor-pointer items-center gap-space-sm rounded-lg px-space-xs py-space-xs transition-colors hover:bg-surface-container-high/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
    >
      <span className="w-6 shrink-0 text-center font-title-code text-title-code tabular-nums text-outline">
        {String(posicao).padStart(2, "0")}
      </span>

      <CapaJogo
        appId={item.app_id}
        nome={item.nome}
        imagemUrl={item.imagem_header}
        className="h-10 w-10 shrink-0 rounded"
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-title-code text-title-code font-bold text-on-surface">
          {item.nome}
        </span>
        <span className="flex min-w-0 gap-space-xxs truncate font-label-caps text-label-caps text-outline">
          {item.generos.slice(0, 2).map((g, i) => (
            <span key={g} className="truncate" style={{ color: corDoGenero(g) }}>
              {i > 0 && <span className="mr-space-xxs text-outline">|</span>}
              {g}
            </span>
          ))}
        </span>
      </div>

      <span className="flex shrink-0 items-center gap-space-xxs font-title-code text-title-code font-bold tabular-nums text-primary">
        <Icone nome="group" className="text-[14px] text-outline" />
        {fmtNumero(item.jogadores_simultaneos)}
      </span>

      {/* Mini-gráfico só quando há série de verdade; o próprio `Sparkline`
          mostra o estado informativo quando faltam pontos. */}
      <span className="hidden w-24 shrink-0 lg:block">
        <Sparkline
          valores={item.serie}
          compacto
          className={subiu ? "text-tertiary" : "text-error"}
        />
      </span>

      {/* Variação não depende só da cor: o ícone de seta carrega o sinal. */}
      <span
        className={`flex w-16 shrink-0 items-center justify-end gap-space-xxs rounded px-space-xs py-space-xxs font-badge-status text-badge-status font-bold tabular-nums ${
          item.variacao === null
            ? "text-outline"
            : subiu
              ? "bg-tertiary/10 text-tertiary"
              : "bg-error/10 text-error"
        }`}
        title={item.variacao === null ? t("catalogoSteam.ranking.semVariacao") : undefined}
      >
        {item.variacao === null ? (
          "—"
        ) : (
          <>
            <Icone nome={subiu ? "arrow_upward" : "arrow_downward"} className="text-[12px]" />
            {fmtPercentual(Math.abs(item.variacao), 1)}
          </>
        )}
      </span>
    </article>
  );
}

export function RankingJogos({
  itens,
  aoAbrir,
}: {
  itens: ItemRanking[];
  aoAbrir: (appId: number) => void;
}) {
  const metade = Math.ceil(itens.length / 2);
  const colunas = [itens.slice(0, metade), itens.slice(metade)];

  return (
    <div className="grid gap-x-space-lg gap-y-space-xxs xl:grid-cols-2">
      {colunas.map((coluna, indiceColuna) => (
        <div key={indiceColuna} className="flex flex-col gap-space-xxs">
          {coluna.map((item, indice) => (
            <LinhaRanking
              key={item.app_id}
              item={item}
              posicao={indiceColuna * metade + indice + 1}
              aoClicar={() => aoAbrir(item.app_id)}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
