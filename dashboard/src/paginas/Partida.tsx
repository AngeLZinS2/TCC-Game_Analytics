/**
 * Placar de uma partida: as dez linhas de fato, separadas por equipe.
 *
 * Porte da tela "Detalhe da Partida" do Stitch: cartao de cabecalho com o
 * selo de vitoria, um bloco por equipe com a tabela de jogadores, e as
 * metricas exclusivas do jogo num bento no rodape.
 */

import { Link, useParams } from "react-router-dom";

import { usePartida } from "../api/consultas";
import type { DetalhePartida, JogadorNaPartida } from "../api/tipos";
import { Consulta, Icone, Selo } from "../componentes/base";
import { RetratoHeroi } from "../componentes/RetratoHeroi";
import { Painel } from "../componentes/hud";
import { PALETA_POLOS } from "../tema";
import { fmtDataHora, fmtDuracao, fmtNumero } from "../utilitarios/formatos";

const EQUIPES = [
  { chave: "radiant", titulo: "Radiant", cor: PALETA_POLOS.positivo },
  { chave: "dire", titulo: "Dire", cor: PALETA_POLOS.negativo },
] as const;

/** Um dado do cabecalho: rotulo pequeno em cima, valor destacado embaixo. */
function Meta({
  rotulo,
  valor,
  cor,
}: {
  rotulo: string;
  valor: React.ReactNode;
  cor?: string;
}) {
  return (
    <div className="flex flex-col">
      <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
        {rotulo}
      </span>
      <span
        className="font-headline-sm text-headline-sm text-on-surface"
        style={cor ? { color: cor } : undefined}
      >
        {valor}
      </span>
    </div>
  );
}

function Placar({
  jogadores,
  cor,
}: {
  jogadores: JogadorNaPartida[];
  cor: string;
}) {
  return (
    <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
            <th className="px-space-md py-space-sm">Herói / Jogador</th>
            <th className="px-space-md py-space-sm text-right">Nível</th>
            <th className="px-space-md py-space-sm text-center">K / D / A</th>
            <th className="px-space-md py-space-sm text-right">LH / DN</th>
            <th className="px-space-md py-space-sm text-right">GPM</th>
            <th className="px-space-md py-space-sm text-right">XPM</th>
            <th className="px-space-md py-space-sm text-right">Economia</th>
            <th className="px-space-md py-space-sm text-right">Dano</th>
            <th className="px-space-md py-space-sm text-right">Objetivos</th>
          </tr>
        </thead>

        <tbody className="font-body-md text-body-sm">
          {jogadores.map((linha, indice) => (
            <tr
              key={linha.slot}
              className={`transition-colors hover:bg-surface-container-high/60 ${
                indice % 2 ? "bg-[#131824]" : "bg-[#10141D]"
              }`}
              style={{ boxShadow: `inset 3px 0 0 ${cor}` }}
            >
              <td className="px-space-md py-space-sm">
                <div className="flex items-center gap-space-sm">
                  <RetratoHeroi
                    nome={linha.personagem ?? "?"}
                    nomeInterno={linha.personagem_interno}
                    className="h-9 w-9"
                  />
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate font-headline-sm text-headline-sm text-on-surface">
                      {linha.personagem ?? "—"}
                    </span>
                    <span className="truncate font-title-code text-title-code text-outline">
                      {linha.jogador ?? "anônimo"}
                    </span>
                  </div>
                </div>
              </td>

              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface">
                {fmtNumero(linha.nivel)}
              </td>

              <td className="px-space-md py-space-sm text-center font-title-code text-title-code tabular-nums">
                <span className="text-tertiary">{linha.kills ?? "—"}</span>
                <span className="text-outline"> / </span>
                <span className="text-error">{linha.deaths ?? "—"}</span>
                <span className="text-outline"> / </span>
                <span className="text-primary">{linha.assists ?? "—"}</span>
              </td>

              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                {linha.last_hits ?? "—"} / {linha.denies ?? "—"}
              </td>
              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                {fmtNumero(linha.economia_por_minuto)}
              </td>
              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                {fmtNumero(linha.experiencia_por_minuto)}
              </td>
              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-primary">
                {fmtNumero(linha.economia)}
              </td>
              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                {fmtNumero(linha.dano_causado)}
              </td>
              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                {fmtNumero(linha.pontos_objetivo)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PartidaPagina() {
  const { idPartida } = useParams();
  const detalhe = usePartida(Number(idPartida));

  return (
    <Consulta estado={detalhe} altura={320}>
      {(dados: DetalhePartida) => {
        const { partida, jogadores } = dados;
        const vencedora = EQUIPES.find((equipe) => equipe.chave === partida.vencedor);

        // As chaves de metricas_extras variam por jogo (e por patch), entao o
        // bento e montado a partir do que veio, nao de uma lista fixa.
        const chavesExtras = [
          ...new Set(jogadores.flatMap((j) => Object.keys(j.metricas_extras ?? {}))),
        ];

        /** Soma da metrica no time todo - o bento mostra o total da partida. */
        const somaExtra = (chave: string) =>
          jogadores.reduce((total, jogador) => {
            const valor = jogador.metricas_extras?.[chave];
            return total + (typeof valor === "number" ? valor : 0);
          }, 0);

        return (
          <>
            {/* ==================== CABECALHO ==================== */}
            <section className="relative overflow-hidden rounded-xl bg-surface-container-low p-space-lg shadow-2xl">
              <div
                className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full blur-3xl"
                style={{
                  background: `${vencedora?.cor ?? PALETA_POLOS.neutro}1a`,
                }}
                aria-hidden
              />

              <Link
                to="/partidas"
                className="relative z-10 inline-flex items-center gap-space-xxs font-title-code text-title-code text-outline transition-colors hover:text-primary"
              >
                <Icone nome="arrow_back" className="text-[16px]" />
                Voltar para partidas
              </Link>

              <div className="relative z-10 mt-space-sm flex flex-col justify-between gap-space-base lg:flex-row lg:items-start">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-space-sm">
                    <span className="font-title-code text-title-code uppercase tracking-wider text-outline">
                      Match ID #{partida.id_externo}
                    </span>
                    {partida.patch && <Selo>Patch {partida.patch}</Selo>}
                    {partida.tipo_partida && (
                      <Selo cor="primario">{partida.tipo_partida}</Selo>
                    )}
                  </div>

                  <h1 className="mt-space-xs font-display-hero text-display-hero uppercase leading-none tracking-tight text-on-surface">
                    {partida.liga_nome ?? "Partida"}
                  </h1>

                  <div className="mt-space-base flex flex-wrap gap-space-xl">
                    <Meta rotulo="Início" valor={fmtDataHora(partida.data_inicio)} />
                    <Meta
                      rotulo="Duração"
                      valor={fmtDuracao(partida.duracao_segundos)}
                      cor={PALETA_POLOS.positivo}
                    />
                    <Meta rotulo="Modo" valor={partida.modo ?? "—"} />
                    <Meta
                      rotulo="Linhas de fato"
                      valor={`${jogadores.length} jogadores`}
                    />
                  </div>
                </div>

                {vencedora ? (
                  <div
                    className="shrink-0 rounded-lg px-space-xl py-space-md text-center"
                    style={{
                      background: `${vencedora.cor}1a`,
                      border: `1px solid ${vencedora.cor}55`,
                    }}
                  >
                    <div
                      className="font-label-caps text-label-caps uppercase tracking-widest opacity-80"
                      style={{ color: vencedora.cor }}
                    >
                      Vitória
                    </div>
                    <div
                      className="font-headline-lg text-headline-lg uppercase leading-none"
                      style={{ color: vencedora.cor }}
                    >
                      {vencedora.titulo}
                    </div>
                  </div>
                ) : (
                  <Selo>Sem vencedor registrado</Selo>
                )}
              </div>
            </section>

            {/* ==================== PLACAR POR EQUIPE ==================== */}
            {EQUIPES.map((equipe) => {
              const linhas = jogadores.filter((j) => j.equipe === equipe.chave);
              if (linhas.length === 0) return null;
              const venceu = linhas.some((j) => j.vitoria);

              return (
                <Painel
                  key={equipe.chave}
                  icone="groups"
                  titulo={
                    <span style={{ color: equipe.cor }}>
                      {equipe.titulo.toUpperCase()}
                    </span>
                  }
                  descricao={`${linhas.length} jogadores`}
                  meta={
                    venceu ? (
                      <Selo cor={equipe.chave === "radiant" ? "positivo" : "negativo"}>
                        Venceu
                      </Selo>
                    ) : (
                      <Selo>Perdeu</Selo>
                    )
                  }
                >
                  <Placar jogadores={linhas} cor={equipe.cor} />
                </Painel>
              );
            })}

            {/* ==================== METRICAS EXCLUSIVAS ==================== */}
            <Painel
              icone="data_object"
              titulo="Métricas exclusivas do jogo"
              descricao="Vão para metricas_extras (JSONB) em vez de virarem colunas que LoL e Valorant nunca preencheriam."
              meta={<Selo cor="primario">{chavesExtras.length} métricas</Selo>}
            >
              {chavesExtras.length === 0 ? (
                <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                  Esta partida não trouxe métricas extras.
                </p>
              ) : (
                <>
                  {/* Bento: o total da partida por metrica. */}
                  <div className="grid grid-cols-2 gap-space-base md:grid-cols-4">
                    {chavesExtras.slice(0, 4).map((chave) => (
                      <div
                        key={chave}
                        className="rounded-lg bg-surface-container-lowest p-space-base"
                      >
                        <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                          {chave.replace(/_/g, " ")}
                        </div>
                        <div className="mt-space-xs font-headline-kpi text-headline-kpi leading-none text-primary">
                          {fmtNumero(somaExtra(chave))}
                        </div>
                        <div className="mt-space-xxs font-body-sm text-body-sm text-outline">
                          somado na partida
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
                    <table className="w-full border-collapse text-left">
                      <thead>
                        <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                          <th className="px-space-md py-space-sm">Jogador</th>
                          {chavesExtras.map((chave) => (
                            <th key={chave} className="px-space-md py-space-sm text-right">
                              {chave.replace(/_/g, " ")}
                            </th>
                          ))}
                        </tr>
                      </thead>

                      <tbody className="font-body-md text-body-sm">
                        {jogadores.map((linha, indice) => (
                          <tr
                            key={linha.slot}
                            className={`transition-colors hover:bg-surface-container-high/60 ${
                              indice % 2 ? "bg-[#131824]" : "bg-[#10141D]"
                            }`}
                          >
                            <td className="px-space-md py-space-sm text-on-surface-variant">
                              {linha.jogador ?? `slot ${linha.slot}`}
                            </td>
                            {chavesExtras.map((chave) => (
                              <td
                                key={chave}
                                className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface"
                              >
                                {fmtNumero(
                                  linha.metricas_extras?.[chave] as
                                    | number
                                    | null
                                    | undefined,
                                )}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </Painel>
          </>
        );
      }}
    </Consulta>
  );
}
