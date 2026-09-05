/**
 * O grafico de uma resposta do assistente.
 *
 * Os pontos vem de `resposta.series`, que o Python monta na MESMA consulta que
 * escreveu o bloco de contexto - nao de reler o texto que o modelo redigiu.
 * Essa e a diferenca entre um grafico conferivel e um grafico bonito: se o
 * modelo inventar um numero na prosa, ele nao aparece aqui.
 *
 * Sem biblioteca: o projeto inteiro desenha barra com CSS (`BarraRanking`,
 * `HistogramaNeon`), e trazer uma dependencia de grafico para colunas simples
 * custaria mais do que resolve.
 */

import type { SerieAssistente } from "../../api/tipos";
import { useEntrarNaTela } from "../../hooks/animacao";
import { fmtCurto, fmtDecimal } from "../../utilitarios/formatos";

/** Quantas marcas de escala desenhar entre zero e o topo. */
const DIVISOES = 4;

/**
 * O eixo comeca em ZERO, nao no menor valor da serie.
 *
 * Um eixo truncado faz 94% e 74% parecerem uma diferenca de dez para um. Num
 * projeto cuja tese e integridade do dado, exagerar a diferenca no desenho
 * seria a mesma falha que o modelo inventar o numero - so que silenciosa.
 */
function escala(valores: number[]): { topo: number; marcas: number[] } {
  const maximo = Math.max(...valores, 1);
  // Arredonda o topo para cima numa potencia de 10 "amigavel" (10, 25, 50,
  // 100, 250...), para as marcas cairem em numeros redondos em vez de 94,1.
  const ordem = 10 ** Math.floor(Math.log10(maximo));
  const passos = [1, 2, 2.5, 5, 10];
  const passo = passos.find((p) => maximo <= p * ordem * DIVISOES) ?? 10;
  const topo = passo * ordem * DIVISOES;
  const marcas = Array.from({ length: DIVISOES + 1 }, (_, i) => (topo / DIVISOES) * i);
  return { topo, marcas };
}

function formatar(valor: number, unidade: string): string {
  if (unidade === "%") return `${fmtDecimal(valor)}%`;
  return fmtCurto(valor);
}

/**
 * A marca do eixo, sem a casa decimal quando ela e zero.
 *
 * "100%" e "75%" no eixo, "94,1%" no rotulo da coluna: a escala e uma regua
 * (numero redondo) e o rotulo e a medida (precisao que importa).
 */
function formatarMarca(valor: number, unidade: string): string {
  if (unidade === "%") return `${Number.isInteger(valor) ? valor : fmtDecimal(valor)}%`;
  return fmtCurto(valor);
}

export function GraficoSerie({ serie }: { serie: SerieAssistente }) {
  const { topo, marcas } = escala(serie.itens.map((i) => i.valor));
  const entrou = useEntrarNaTela(serie.chave + serie.itens.length);

  return (
    <figure className="flex flex-col gap-space-sm">
      <figcaption className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-primary">
        <span aria-hidden>✦</span>
        {serie.titulo}
      </figcaption>

      <div className="flex gap-space-xs">
        {/* Eixo vertical: os rotulos das marcas, alinhados as linhas de grade. */}
        <div
          className="flex h-56 shrink-0 flex-col-reverse justify-between font-badge-status text-badge-status tabular-nums text-outline"
          aria-hidden
        >
          {marcas.map((marca) => (
            <span key={marca} className="leading-none">
              {formatarMarca(marca, serie.unidade)}
            </span>
          ))}
        </div>

        <div className="relative min-w-0 flex-1">
          {/* Grade: uma linha por marca, para o olho medir a coluna sem contar.
              Fica FORA do container que rola - a regua e do grafico, nao das
              colunas: ela nao deve deslizar junto quando eles rolam. */}
          <div
            className="absolute inset-x-0 top-0 flex h-56 flex-col-reverse justify-between"
            aria-hidden
          >
            {marcas.map((marca) => (
              <div key={marca} className="border-t border-outline-variant/20" />
            ))}
          </div>

          {/*
            Colunas e rotulos no MESMO container rolavel, e cada rotulo dentro
            da sua coluna. Quando eram duas faixas irmas, a de baixo nao rolava
            junto - e, pior, empurrava a pagina inteira na largura: em 390px o
            corpo ganhava rolagem horizontal por causa dos 8 rotulos de 52px.
          */}
          <div className="rolagem-discreta relative overflow-x-auto">
            <div className="flex min-w-full gap-space-sm">
              {serie.itens.map((ponto, indice) => {
                const altura = (ponto.valor / topo) * 100;
                const lider = indice === 0;
                return (
                  <div
                    key={ponto.rotulo}
                    className="group flex min-w-[52px] flex-1 flex-col"
                    title={
                      ponto.detalhe
                        ? `${ponto.rotulo}: ${formatar(ponto.valor, serie.unidade)} (${ponto.detalhe})`
                        : `${ponto.rotulo}: ${formatar(ponto.valor, serie.unidade)}`
                    }
                  >
                    <div className="flex h-56 flex-col justify-end pt-6">
                      <span className="mb-space-xxs text-center font-badge-status text-badge-status tabular-nums text-on-surface-variant transition-colors group-hover:text-primary">
                        {formatar(ponto.valor, serie.unidade)}
                      </span>
                      <div
                        className={`w-full rounded-t ${
                          lider
                            ? "bg-gradient-to-t from-primary-container to-primary shadow-[0_0_12px_rgba(0,229,255,0.35)]"
                            : "bg-gradient-to-t from-primary-container/50 to-primary/60"
                        }`}
                        style={{
                          height: `${entrou ? Math.max(2, altura) : 0}%`,
                          transition: "height 700ms cubic-bezier(0.16, 1, 0.3, 1)",
                          // Escalona a entrada da esquerda para a direita: le-se
                          // o ranking na ordem em que ele existe.
                          transitionDelay: `${indice * 45}ms`,
                        }}
                      />
                    </div>

                    <span
                      className="mt-space-xs truncate text-center font-badge-status text-badge-status text-outline"
                      title={ponto.rotulo}
                    >
                      {ponto.rotulo}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/*
        Tabela equivalente, so para leitor de tela: um grafico feito de divs
        nao diz nada em audio, e repetir os numeros aqui e mais honesto do que
        um `aria-label` resumindo "grafico de winrate".
      */}
      <table className="sr-only">
        <caption>{serie.titulo}</caption>
        <tbody>
          {serie.itens.map((ponto) => (
            <tr key={ponto.rotulo}>
              <th scope="row">{ponto.rotulo}</th>
              <td>
                {formatar(ponto.valor, serie.unidade)}
                {ponto.detalhe ? ` (${ponto.detalhe})` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
