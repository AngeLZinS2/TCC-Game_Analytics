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

import type { ResumoConfrontos } from "../api/tipos";
import { AreaNeon } from "./graficos/AreaNeon";
import { HistogramaNeon } from "./graficos/HistogramaNeon";
import { BarraSegmentada, KpiHud, Painel, Sparkline } from "./hud";
import { PALETA_POLOS } from "../tema";
import { fmtDataCurta, fmtNumero, fmtPercentual } from "../utilitarios/formatos";

export function EstatisticasConfrontos({ dados }: { dados: ResumoConfrontos }) {
  const serie = dados.por_dia.map((ponto) => ponto.partidas);
  const ladoA = (dados.winrate_lado_a ?? 50) / 100;

  return (
    <>
      <section className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-4">
        <KpiHud
          etiqueta="Confrontos decididos"
          canto="CALENDÁRIO"
          valor={fmtNumero(dados.decididos)}
          valorNumerico={dados.decididos}
          formatarValor={fmtNumero}
          rotulo="Séries com resultado publicado"
          acento="primaria"
          notaVariacao={`${fmtDataCurta(dados.primeiro_confronto)} — ${fmtDataCurta(
            dados.ultimo_confronto,
          )}`}
        >
          <Sparkline valores={serie} />
        </KpiHud>

        <KpiHud
          etiqueta="Equipes no calendário"
          canto="DIMENSÃO"
          valor={fmtNumero(dados.equipes)}
          valorNumerico={dados.equipes}
          formatarValor={fmtNumero}
          rotulo="Times que apareceram em algum confronto"
          acento="secundaria"
          notaVariacao={`${fmtNumero(dados.torneios)} torneios`}
        />

        {/*
          O análogo de "vitórias do lado Radiant". Aqui não há lado fixo: é a
          frequência com que o time listado em primeiro venceu. Perto de 50%
          significa que a ordem da fonte não carrega vantagem — que é a leitura
          honesta, e é o que o modelo de previsão usa como intercepto.
        */}
        <KpiHud
          etiqueta="Vantagem do lado A"
          canto={ladoA > 0.55 || ladoA < 0.45 ? "DESEQUILÍBRIO" : "EQUILÍBRIO"}
          valor={fmtPercentual((dados.winrate_lado_a ?? 0), 1)}
          valorNumerico={dados.winrate_lado_a}
          formatarValor={(v) => fmtPercentual(v, 1)}
          rotulo="Vitórias de quem é listado em primeiro"
          acento="terciaria"
          notaVariacao={`${fmtNumero(dados.vitorias_lado_a)} de ${fmtNumero(
            dados.decididos,
          )}`}
        >
          <div className="mt-space-md">
            <BarraSegmentada
              fracaoA={ladoA}
              corA={PALETA_POLOS.positivo}
              corB={PALETA_POLOS.negativo}
              legendaEsquerda={`Lado A ${fmtPercentual(dados.winrate_lado_a ?? 0, 1)}`}
              legendaDireita={`Lado B ${fmtPercentual(100 - (dados.winrate_lado_a ?? 0), 1)}`}
            />
          </div>
        </KpiHud>

        <KpiHud
          etiqueta="Confrontos agendados"
          canto="POR VIR"
          valor={fmtNumero(dados.futuros)}
          valorNumerico={dados.futuros}
          formatarValor={fmtNumero}
          rotulo="Ainda sem resultado publicado"
          acento="primaria"
          notaVariacao="sem duração nem jogador: o ticker não publica"
        />
      </section>

      <section className="grid grid-cols-1 gap-space-base xl:grid-cols-2">
        <Painel
          icone="bar_chart"
          titulo="Formato das séries"
          descricao="Melhor-de-N por confronto. É o que substitui a distribuição de duração — a fonte não publica quanto tempo a partida levou."
        >
          <HistogramaNeon
            faixas={dados.por_formato.map((f) => ({
              rotulo: f.rotulo,
              valor: f.confrontos,
            }))}
            formatarValor={fmtNumero}
            rodapeEsquerda={
              <span>
                {fmtNumero(dados.por_formato.length)} formatos no calendário
              </span>
            }
            rodapeDireita={
              <span className="text-on-surface">
                {fmtNumero(dados.decididos + dados.futuros)} confrontos
              </span>
            }
          />
        </Painel>

        <Painel
          icone="show_chart"
          titulo="Confrontos por dia"
          descricao="Data de disputa do confronto, não a da coleta."
        >
          <AreaNeon
            pontos={dados.por_dia.map((p) => ({
              rotulo: fmtDataCurta(p.data),
              valor: p.partidas,
            }))}
            formatarValor={fmtNumero}
            rodapeEsquerda={
              <span>
                Pico diário:{" "}
                <strong className="text-on-surface">
                  {fmtNumero(Math.max(0, ...serie))} confrontos
                </strong>
              </span>
            }
            rodapeDireita={
              <span>{fmtNumero(dados.por_dia.length)} dias com confronto</span>
            }
          />
        </Painel>
      </section>
    </>
  );
}
