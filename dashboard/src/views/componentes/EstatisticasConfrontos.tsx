/**
 * A estatística da tela de Partidas para quem não tem partida detalhada.
 *
 * `dim_partida` — com duração, jogador e herói — só existe para Dota 2, porque
 * só a OpenDota entrega esse grão. Os outros treze esportes abriam a tela com
 * tudo zerado: zero partidas, zero jogadores, duração nula, gráficos vazios —
 * tendo confronto, equipe, torneio e placar no banco.
 *
 * Aqui os mesmos quatro KPIs e os mesmos dois gráficos são respondidos no grão
 * que esses jogos têm: a série, não a partida dentro dela. Nada é convertido
 * nem estimado — o que a fonte não publica (duração, jogadores) simplesmente
 * não aparece, em vez de aparecer como zero.
 */

import { useTranslation } from "react-i18next";

import type { ResumoConfrontos } from "@models/api/tipos";
import { AreaNeon } from "./graficos/AreaNeon";
import { HistogramaNeon } from "./graficos/HistogramaNeon";
import { BarraSegmentada, KpiHud, Painel, Sparkline } from "./hud";
import { PALETA_POLOS } from "@views/tema";
import { fmtDataCurta, fmtNumero, fmtPercentual } from "@util/formatos";

export function EstatisticasConfrontos({ dados }: { dados: ResumoConfrontos }) {
  const { t } = useTranslation();
  const serie = dados.por_dia.map((ponto) => ponto.partidas);
  const ladoA = (dados.winrate_lado_a ?? 50) / 100;

  return (
    <>
      <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
        <KpiHud
          etiqueta={t("estatisticasConfrontos.confrontosDecididos")}
          canto={t("estatisticasConfrontos.calendario")}
          valor={fmtNumero(dados.decididos)}
          valorNumerico={dados.decididos}
          formatarValor={fmtNumero}
          rotulo={t("estatisticasConfrontos.seriesComResultado")}
          acento="primaria"
          notaVariacao={`${fmtDataCurta(dados.primeiro_confronto)} — ${fmtDataCurta(
            dados.ultimo_confronto,
          )}`}
        >
          <Sparkline valores={serie} />
        </KpiHud>

        <KpiHud
          etiqueta={t("estatisticasConfrontos.equipesNoCalendario")}
          canto={t("estatisticasConfrontos.dimensao")}
          valor={fmtNumero(dados.equipes)}
          valorNumerico={dados.equipes}
          formatarValor={fmtNumero}
          rotulo={t("estatisticasConfrontos.timesQueApareceram")}
          acento="secundaria"
          notaVariacao={t("estatisticasConfrontos.torneios", { n: fmtNumero(dados.torneios) })}
        />

        {/*
          O análogo de "vitórias do lado Radiant". Aqui não há lado fixo: é a
          frequência com que o time listado em primeiro venceu. Perto de 50%
          significa que a ordem da fonte não carrega vantagem — que é a leitura
          honesta, e é o que o modelo de previsão usa como intercepto.
        */}
        <KpiHud
          etiqueta={t("estatisticasConfrontos.vantagemLadoA")}
          canto={
            ladoA > 0.55 || ladoA < 0.45
              ? t("estatisticasConfrontos.desequilibrio")
              : t("estatisticasConfrontos.equilibrio")
          }
          valor={fmtPercentual((dados.winrate_lado_a ?? 0), 1)}
          valorNumerico={dados.winrate_lado_a}
          formatarValor={(v) => fmtPercentual(v, 1)}
          rotulo={t("estatisticasConfrontos.vitoriasDeQuemListado")}
          acento="terciaria"
          notaVariacao={t("estatisticasConfrontos.deTotal", {
            a: fmtNumero(dados.vitorias_lado_a),
            b: fmtNumero(dados.decididos),
          })}
        >
          <div className="mt-space-md">
            <BarraSegmentada
              fracaoA={ladoA}
              corA={PALETA_POLOS.positivo}
              corB={PALETA_POLOS.negativo}
              legendaEsquerda={t("estatisticasConfrontos.ladoALabel", {
                pct: fmtPercentual(dados.winrate_lado_a ?? 0, 1),
              })}
              legendaDireita={t("estatisticasConfrontos.ladoBLabel", {
                pct: fmtPercentual(100 - (dados.winrate_lado_a ?? 0), 1),
              })}
            />
          </div>
        </KpiHud>

        <KpiHud
          etiqueta={t("estatisticasConfrontos.confrontosAgendados")}
          canto={t("estatisticasConfrontos.porVir")}
          valor={fmtNumero(dados.futuros)}
          valorNumerico={dados.futuros}
          formatarValor={fmtNumero}
          rotulo={t("estatisticasConfrontos.semResultado")}
          acento="primaria"
          notaVariacao={t("estatisticasConfrontos.semDuracaoNemJogador")}
        />
      </section>

      <section className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
        <Painel
          icone="bar_chart"
          titulo={t("estatisticasConfrontos.formatoDasSeries")}
          descricao={t("estatisticasConfrontos.formatoDescricao")}
        >
          <HistogramaNeon
            faixas={dados.por_formato.map((f) => ({
              rotulo: f.rotulo,
              valor: f.confrontos,
            }))}
            formatarValor={fmtNumero}
            rodapeEsquerda={
              <span>
                {t("estatisticasConfrontos.formatosNoCalendario", { n: fmtNumero(dados.por_formato.length) })}
              </span>
            }
            rodapeDireita={
              <span className="text-on-surface">
                {t("estatisticasConfrontos.confrontosTotal", { n: fmtNumero(dados.decididos + dados.futuros) })}
              </span>
            }
          />
        </Painel>

        <Painel
          icone="show_chart"
          titulo={t("estatisticasConfrontos.confrontosPorDia")}
          descricao={t("estatisticasConfrontos.dataDeDisputa")}
        >
          <AreaNeon
            pontos={dados.por_dia.map((p) => ({
              rotulo: fmtDataCurta(p.data),
              valor: p.partidas,
            }))}
            formatarValor={fmtNumero}
            rodapeEsquerda={
              <span>
                {t("estatisticasConfrontos.picoDiario")}{" "}
                <strong className="text-on-surface">
                  {t("estatisticasConfrontos.confrontosTotal", { n: fmtNumero(Math.max(0, ...serie)) })}
                </strong>
              </span>
            }
            rodapeDireita={
              <span>{t("estatisticasConfrontos.diasComConfronto", { n: fmtNumero(dados.por_dia.length) })}</span>
            }
          />
        </Painel>
      </section>
    </>
  );
}
