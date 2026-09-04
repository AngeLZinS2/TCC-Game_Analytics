/**
 * Serie temporal em area, no estilo do desenho do Stitch.
 *
 * E SVG escrito a mao, nao Recharts. O motivo nao e economia de dependencia: o
 * desenho pede uma curva com gradiente de traco (ciano -> violeta -> verde),
 * brilho por `drop-shadow`, area preenchida com um segundo gradiente e o ponto
 * de maximo destacado com anel. Reproduzir isso por cima de uma biblioteca de
 * grafico da mais trabalho do que desenhar, e o resultado fica preso ao que a
 * biblioteca deixa customizar.
 *
 * O que o mockup chama de "tooltip flutuante simulado" aqui e de verdade: o
 * ponteiro sobre o grafico marca o ponto mais proximo e mostra o valor.
 */

import { useId, useMemo, useState } from "react";

import { useEntrarNaTela } from "../../hooks/animacao";

export interface PontoArea {
  rotulo: string;
  valor: number;
  /** Texto opcional do tooltip. Sem ele, mostra `rotulo` e `valor`. */
  detalhe?: string;
}

const LARGURA = 500;
const ALTURA = 150;

/**
 * Curva suave passando por todos os pontos (Catmull-Rom convertida em Bezier).
 *
 * A alternativa - `type="linear"` - foi a escolha certa nos graficos de
 * snapshot, onde interpolar sugeriria medidas que nunca existiram. Aqui a serie
 * e contagem por dia, uma grandeza continua no tempo, e o desenho pede a curva.
 */
function caminhoSuave(pontos: { x: number; y: number }[]): string {
  if (pontos.length < 2) return "";

  const partes = [`M ${pontos[0].x},${pontos[0].y}`];

  for (let i = 0; i < pontos.length - 1; i += 1) {
    const anterior = pontos[i - 1] ?? pontos[i];
    const atual = pontos[i];
    const proximo = pontos[i + 1];
    const seguinte = pontos[i + 2] ?? proximo;

    // Tensao 1/6: o valor que mantem a curva colada nos pontos sem estourar
    // acima do maximo, que num grafico de contagem seria ler errado.
    const c1x = atual.x + (proximo.x - anterior.x) / 6;
    const c1y = atual.y + (proximo.y - anterior.y) / 6;
    const c2x = proximo.x - (seguinte.x - atual.x) / 6;
    const c2y = proximo.y - (seguinte.y - atual.y) / 6;

    partes.push(
      `C ${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${proximo.x.toFixed(1)},${proximo.y.toFixed(1)}`,
    );
  }

  return partes.join(" ");
}

export function AreaNeon({
  pontos,
  formatarValor,
  rodapeEsquerda,
  rodapeDireita,
}: {
  pontos: PontoArea[];
  formatarValor: (valor: number) => string;
  rodapeEsquerda?: React.ReactNode;
  rodapeDireita?: React.ReactNode;
}) {
  // `useId` porque dois graficos na mesma pagina com o mesmo id de gradiente
  // fazem o segundo herdar o primeiro.
  const id = useId().replace(/:/g, "");
  const [ativo, setAtivo] = useState<number | null>(null);
  // Rearma a animacao quando a serie muda (trocar o periodo, abrir outro
  // jogo) - o traco volta a se desenhar em vez de saltar pra forma nova.
  const entrou = useEntrarNaTela(pontos.map((p) => p.valor).join(","));

  const { coordenadas, maximo, indiceMaximo, marcasY } = useMemo(() => {
    const valores = pontos.map((p) => p.valor);
    const maximo = Math.max(...valores, 1);
    const indiceMaximo = valores.indexOf(Math.max(...valores));

    const coordenadas = pontos.map((ponto, indice) => ({
      x: pontos.length === 1 ? LARGURA / 2 : (indice / (pontos.length - 1)) * LARGURA,
      // 8px de folga no topo para o anel do ponto de maximo nao ser cortado.
      y: ALTURA - (ponto.valor / maximo) * (ALTURA - 12) - 6,
    }));

    const marcasY = [1, 0.5, 0].map((fracao) => ({
      fracao,
      rotulo: formatarValor(maximo * fracao),
    }));

    return { coordenadas, maximo, indiceMaximo, marcasY };
  }, [pontos, formatarValor]);

  if (pontos.length === 0) {
    return (
      <p className="flex h-44 items-center justify-center font-body-sm text-body-sm text-outline">
        Nenhum ponto coletado ainda.
      </p>
    );
  }

  const linha = caminhoSuave(coordenadas);
  const area = `${linha} L ${LARGURA},${ALTURA} L 0,${ALTURA} Z`;
  const pontoAtivo = ativo === null ? null : pontos[ativo];

  return (
    <div className="relative">
      {/* Tooltip: acompanha o ponto marcado. */}
      {pontoAtivo && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded border border-outline-variant/50 bg-surface-container-lowest/95 px-space-md py-space-sm shadow-xl"
          style={{
            left: `calc(2rem + ${(coordenadas[ativo!].x / LARGURA) * 100}% * 0.94)`,
            top: `${(coordenadas[ativo!].y / ALTURA) * 176 - 8}px`,
          }}
        >
          <div className="font-label-caps text-label-caps uppercase tracking-widest text-primary">
            {pontoAtivo.rotulo}
          </div>
          <div className="font-headline-sm text-headline-sm text-on-surface">
            {pontoAtivo.detalhe ?? formatarValor(pontoAtivo.valor)}
          </div>
        </div>
      )}

      <div className="relative">
        {/* Grade e rotulos do eixo Y, atras do SVG. */}
        <div className="absolute inset-0 flex flex-col justify-between font-label-caps text-label-caps text-outline">
          {marcasY.map((marca) => (
            <div key={marca.fracao} className="flex w-full items-center gap-space-xs">
              <span className="w-8 shrink-0 text-right">{marca.rotulo}</span>
              <span className="h-[1px] flex-1 bg-outline-variant/30" />
            </div>
          ))}
        </div>

        <svg
          className="h-44 w-full overflow-visible pl-8 pr-2"
          viewBox={`0 0 ${LARGURA} ${ALTURA}`}
          preserveAspectRatio="none"
          role="img"
          aria-label={`Série de ${pontos.length} pontos, máximo de ${formatarValor(maximo)}`}
          onMouseLeave={() => setAtivo(null)}
          onMouseMove={(evento) => {
            const caixa = evento.currentTarget.getBoundingClientRect();
            const fracao = (evento.clientX - caixa.left) / caixa.width;
            const indice = Math.round(fracao * (pontos.length - 1));
            setAtivo(Math.min(pontos.length - 1, Math.max(0, indice)));
          }}
        >
          <defs>
            <linearGradient id={`area-${id}`} x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#00daf3" stopOpacity="0.45" />
              <stop offset="60%" stopColor="#4720ca" stopOpacity="0.15" />
              <stop offset="100%" stopColor="#10131a" stopOpacity="0" />
            </linearGradient>
            <linearGradient id={`traco-${id}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#00e5ff" />
              <stop offset="70%" stopColor="#c9bfff" />
              <stop offset="100%" stopColor="#16ef7a" />
            </linearGradient>
          </defs>

          <path
            d={area}
            fill={`url(#area-${id})`}
            opacity={entrou ? 1 : 0}
            style={{ transition: "opacity 900ms ease-out 400ms" }}
          />
          <path
            className="drop-shadow-[0_0_8px_rgba(0,229,255,0.8)]"
            d={linha}
            fill="none"
            stroke={`url(#traco-${id})`}
            strokeWidth="3"
            vectorEffect="non-scaling-stroke"
            // O traco se desenha da esquerda pra direita: `pathLength=1`
            // normaliza a curva pra 1 unidade, entao o dashoffset nao
            // depende do comprimento real (que muda com a serie).
            pathLength={1}
            strokeDasharray={1}
            strokeDashoffset={entrou ? 0 : 1}
            style={{ transition: "stroke-dashoffset 1100ms cubic-bezier(0.16, 1, 0.3, 1)" }}
          />

          {coordenadas.map((coordenada, indice) => {
            const eMaximo = indice === indiceMaximo && pontos.length > 1;
            const eAtivo = indice === ativo;
            // Escalona a chegada de cada ponto acompanhando o traco: o ponto
            // so "pousa" quando a linha, na velocidade do dashoffset acima,
            // teria acabado de passar por ele.
            const atraso = 200 + (indice / Math.max(1, coordenadas.length - 1)) * 900;

            return (
              <circle
                key={indice}
                cx={coordenada.x}
                cy={coordenada.y}
                r={entrou ? (eMaximo || eAtivo ? 6 : 4) : 0}
                className={
                  eMaximo || eAtivo
                    ? "fill-primary-container stroke-surface stroke-2 drop-shadow-[0_0_8px_#00e5ff]"
                    : "fill-primary"
                }
                vectorEffect="non-scaling-stroke"
                style={
                  eAtivo
                    ? undefined
                    : { transition: `r 300ms ease-out ${atraso}ms` }
                }
              />
            );
          })}
        </svg>
      </div>

      {/* Rotulos do eixo X. Series longas mostram so alguns, senao viram borrao. */}
      <div className="flex justify-between pl-8 pr-2 pt-space-xs font-label-caps text-label-caps text-outline">
        {pontos.map((ponto, indice) => {
          const passo = Math.ceil(pontos.length / 8);
          if (indice % passo !== 0 && indice !== pontos.length - 1) return null;
          return (
            <span
              key={indice}
              className={indice === indiceMaximo ? "font-bold text-primary" : undefined}
            >
              {ponto.rotulo}
            </span>
          );
        })}
      </div>

      {(rodapeEsquerda || rodapeDireita) && (
        <div className="-mx-space-lg -mb-space-lg mt-space-lg flex items-center justify-between rounded-b bg-surface-container-lowest/60 px-space-lg py-space-sm text-outline">
          <span className="font-body-sm text-body-sm">{rodapeEsquerda}</span>
          <span className="font-title-code text-title-code text-primary">
            {rodapeDireita}
          </span>
        </div>
      )}
    </div>
  );
}
