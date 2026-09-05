/**
 * A ficha de um personagem — o equivalente da tela de agente do op.gg.
 *
 * Três blocos, na ordem em que a pergunta chega:
 *
 * 1. Quem é: retrato, função, lore. Vem da API do próprio jogo
 *    (`dim_personagem.metadados`).
 * 2. Como vai: o desempenho geral, nas mesmas colunas da tabela de personagens,
 *    com o intervalo de confiança do winrate — o mesmo tratamento que a lista.
 * 3. Onde vai bem: o recorte POR MAPA. É o que a lista (uma linha por
 *    personagem) não cabe mostrar, e onde "Chamber é forte em Ascent, fraco em
 *    Fracture" aparece. Só Valorant tem, por ora.
 *
 * O que a fonte não dá fica de fora, não vira zero: um jogo sem a parte
 * estática mostra só os números; um sem número mostra só quem é.
 */

import { Link, useParams } from "react-router-dom";

import { useDetalhePersonagem } from "../api/consultas";
import type {
  DetalhePersonagem,
  EstatisticaMapa,
  MetricaEsporte,
} from "../api/tipos";
import { Consulta, Icone, Selo } from "../componentes/base";
import { BarraFina, KpiHud, Painel } from "../componentes/hud";
import { PALETA_POLOS } from "../tema";
import { intervaloWilson } from "../utilitarios/estatistica";
import { fmtDecimal, fmtNumero, fmtPercentual } from "../utilitarios/formatos";

/** Formata um valor de métrica pela definição do perfil (casas + unidade). */
function fmtMetrica(valor: number | null | undefined, m: MetricaEsporte): string {
  if (valor === null || valor === undefined) return "—";
  return `${fmtDecimal(valor, m.casas)}${m.unidade}`;
}

/** Uma célula de estatística: rótulo em cima, número embaixo. */
function Numero({
  rotulo,
  valor,
  titulo,
}: {
  rotulo: string;
  valor: React.ReactNode;
  titulo?: string;
}) {
  return (
    <div className="flex flex-col gap-space-xxs" title={titulo}>
      <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
        {rotulo}
      </span>
      <span className="font-headline-sm text-headline-sm tabular-nums text-on-surface">
        {valor}
      </span>
    </div>
  );
}

/** A tabela por mapa: winrate + as métricas do perfil, um mapa por linha. */
function TabelaMapas({
  linhas,
  metricas,
  recorte,
}: {
  linhas: EstatisticaMapa[];
  metricas: MetricaEsporte[];
  recorte: string;
}) {
  return (
    <div className="rolagem-discreta overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
            <th className="px-space-md py-space-sm">{recorte === "rota" ? "Rota" : "Mapa"}</th>
            <th className="px-space-md py-space-sm text-right">Partidas</th>
            <th className="px-space-md py-space-sm">Winrate</th>
            {metricas.map((m) => (
              <th key={m.chave} className="px-space-md py-space-sm text-right" title={m.descricao}>
                {m.rotulo}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="font-body-md text-body-sm">
          {linhas.map((linha) => {
            const acima = linha.winrate > 50;
            const cor = acima ? PALETA_POLOS.positivo : PALETA_POLOS.negativo;
            return (
              <tr
                key={linha.mapa}
                className="border-b border-outline-variant/20 last:border-0"
              >
                <td className="px-space-md py-space-sm font-title-code text-title-code text-on-surface">
                  {linha.mapa}
                </td>
                <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                  {fmtNumero(linha.partidas)}
                </td>
                <td className="px-space-md py-space-sm">
                  <div className="flex items-center gap-space-sm">
                    <div className="hidden w-24 sm:block">
                      <BarraFina largura={linha.winrate} cor={cor} />
                    </div>
                    <span
                      className="font-title-code text-title-code tabular-nums"
                      style={{ color: cor }}
                    >
                      {fmtPercentual(linha.winrate)}
                    </span>
                  </div>
                </td>
                {metricas.map((m) => (
                  <td
                    key={m.chave}
                    className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant"
                  >
                    {fmtMetrica(linha.metricas[m.chave], m)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Ficha({ dados }: { dados: DetalhePersonagem }) {
  const { geral, perfil, por_mapa: porMapa } = dados;
  const ic = geral ? intervaloWilson(geral.vitorias, geral.partidas) : null;

  const melhorMapa = porMapa[0];
  const piorMapa = porMapa.at(-1);

  // O recorte não é "mapa" em todo jogo: Valorant é por mapa, LoL por rota.
  // A palavra vem do que a fonte chamou o campo `papel` do personagem —
  // "Meio"/"Suporte" são rotas, "Ascent"/"Bind" são mapas.
  const recorte =
    dados.jogo === "leagueoflegends" ? "rota" : "mapa";

  return (
    <div className="flex flex-col gap-space-lg">
      {/* ==================== QUEM É ==================== */}
      <section className="relative overflow-hidden rounded-xl bg-surface-container-low shadow-2xl">
        {dados.fundo && (
          <img
            src={dados.fundo}
            alt=""
            aria-hidden
            className="pointer-events-none absolute right-0 top-0 h-full w-1/2 object-cover opacity-20"
          />
        )}
        <div className="relative flex flex-col gap-space-base p-space-lg sm:flex-row sm:items-center">
          {dados.retrato ? (
            <img
              src={dados.retrato}
              alt={dados.nome}
              className="h-40 w-40 shrink-0 self-center object-contain sm:self-auto"
            />
          ) : dados.icone ? (
            <img
              src={dados.icone}
              alt={dados.nome}
              className="h-24 w-24 shrink-0 self-center rounded bg-surface-container-highest p-space-sm sm:self-auto"
            />
          ) : null}

          <div className="flex flex-col gap-space-sm">
            <div className="flex flex-wrap items-center gap-space-sm">
              <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-primary drop-shadow-[0_0_12px_rgba(0,229,255,0.4)]">
                {dados.nome}
              </h1>
              {dados.papel && <Selo cor="primario">{dados.papel}</Selo>}
            </div>
            {dados.descricao && (
              <p className="max-w-2xl font-body-md text-body-md text-on-surface-variant">
                {dados.descricao}
              </p>
            )}
            <Link
              to="/herois"
              className="flex w-fit items-center gap-space-xxs font-title-code text-title-code text-outline transition-colors hover:text-primary"
            >
              <Icone nome="arrow_back" className="text-[16px]" />
              voltar aos {perfil.substantivo_plural}
            </Link>
          </div>
        </div>
      </section>

      {/* ==================== COMO VAI (geral) ==================== */}
      {geral && geral.partidas > 0 ? (
        <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
          <KpiHud
            etiqueta="Winrate"
            canto="GERAL"
            valor={fmtPercentual(geral.winrate)}
            rotulo={
              ic
                ? `IC 95%: ${fmtDecimal(ic.minimo * 100, 1)}–${fmtDecimal(
                    ic.maximo * 100,
                    1,
                  )}%`
                : "sem intervalo"
            }
            acento="secundaria"
            notaVariacao={`${fmtNumero(geral.partidas)} partidas`}
          />
          {perfil.metricas.slice(0, 3).map((m, i) => (
            <KpiHud
              key={m.chave}
              etiqueta={m.rotulo}
              canto={m.unidade === "%" ? "TAXA" : "MÉDIA"}
              valor={fmtMetrica(geral.metricas[m.chave], m)}
              rotulo={m.descricao}
              acento={i === 0 ? "primaria" : "terciaria"}
            />
          ))}
        </section>
      ) : (
        <Painel icone="query_stats" titulo="Sem estatística">
          <p className="font-body-md text-body-md text-on-surface-variant">
            Nenhuma fonte publicou número de desempenho para {dados.nome} ainda.
          </p>
        </Painel>
      )}

      {/* ==================== ONDE VAI BEM (por mapa) ==================== */}
      {porMapa.length > 0 && (
        <Painel
          icone="map"
          titulo={`Desempenho por ${recorte}`}
          descricao={`${perfil.nota_fonte} A média geral acima esconde a variação entre ${recorte}s.`}
          meta={<Selo>{porMapa.length} {recorte}s</Selo>}
        >
          {melhorMapa && piorMapa && melhorMapa.mapa !== piorMapa.mapa && (
            <div className="flex flex-wrap gap-space-lg">
              <Numero
                rotulo={`Melhor ${recorte}`}
                valor={
                  <span style={{ color: PALETA_POLOS.positivo }}>
                    {melhorMapa.mapa} · {fmtPercentual(melhorMapa.winrate)}
                  </span>
                }
                titulo={`${fmtNumero(melhorMapa.partidas)} partidas`}
              />
              <Numero
                rotulo={`Pior ${recorte}`}
                valor={
                  <span style={{ color: PALETA_POLOS.negativo }}>
                    {piorMapa.mapa} · {fmtPercentual(piorMapa.winrate)}
                  </span>
                }
                titulo={`${fmtNumero(piorMapa.partidas)} partidas`}
              />
              <Numero
                rotulo="Amplitude"
                valor={`${fmtDecimal(melhorMapa.winrate - piorMapa.winrate, 1)} pp`}
                titulo={`diferença entre ${recorte === "rota" ? "a melhor e a pior rota" : "o melhor e o pior mapa"}`}
              />
            </div>
          )}
          <TabelaMapas linhas={porMapa} metricas={perfil.metricas} recorte={recorte} />
        </Painel>
      )}

      {/* ==================== HABILIDADES ==================== */}
      {dados.habilidades.length > 0 && (
        <Painel
          icone="bolt"
          titulo="Habilidades"
          descricao={
            dados.habilidades.some((h) => h.video)
              ? "Clipe e texto oficiais da Riot."
              : undefined
          }
        >
          <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2">
            {dados.habilidades.map((hab) => (
              <div
                key={hab.nome}
                className="flex flex-col overflow-hidden rounded-lg bg-surface-container-lowest"
              >
                {hab.video && (
                  <video
                    src={hab.video}
                    muted
                    loop
                    playsInline
                    autoPlay
                    // O clipe da Riot roda em silencio e em loop, como na
                    // ficha oficial - e uma pré-visualização da mecânica, não
                    // um vídeo para assistir com áudio.
                    className="aspect-video w-full bg-black object-cover"
                    controlsList="nodownload"
                  />
                )}
                <div className="flex gap-space-base p-space-base">
                  {hab.icone && (
                    <img
                      src={hab.icone}
                      alt=""
                      aria-hidden
                      className="h-10 w-10 shrink-0 opacity-90"
                    />
                  )}
                  <div className="flex flex-col gap-space-xxs">
                    <div className="flex items-center gap-space-xs">
                      <span className="font-title-code text-title-code text-on-surface">
                        {hab.nome}
                      </span>
                      {hab.slot && (
                        <span className="font-badge-status text-badge-status uppercase tracking-wider text-outline">
                          {hab.slot}
                        </span>
                      )}
                    </div>
                    {hab.descricao && (
                      <p className="font-body-sm text-body-sm text-on-surface-variant">
                        {hab.descricao}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Painel>
      )}
    </div>
  );
}

export function HeroiDetalhePagina() {
  const { idPersonagem } = useParams();
  const id = Number(idPersonagem);
  const detalhe = useDetalhePersonagem(id);

  return (
    <Consulta estado={detalhe} altura={320}>
      {(dados) => <Ficha dados={dados} />}
    </Consulta>
  );
}
