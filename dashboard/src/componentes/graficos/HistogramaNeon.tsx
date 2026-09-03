/**
 * Histograma de colunas, no estilo do desenho do Stitch.
 *
 * A coluna modal (a mais alta) ganha rotulo flutuante e brilho - o desenho
 * chama de "Modal Peak". Isso e legitimo aqui e nao seria num ranking: num
 * histograma a moda E a leitura principal, entao destaca-la reforca o que o
 * grafico existe para dizer, em vez de duplicar o comprimento em cor.
 */

export interface FaixaHistograma {
  rotulo: string;
  valor: number;
}

export function HistogramaNeon({
  faixas,
  formatarValor,
  rodapeEsquerda,
  rodapeDireita,
}: {
  faixas: FaixaHistograma[];
  formatarValor: (valor: number) => string;
  rodapeEsquerda?: React.ReactNode;
  rodapeDireita?: React.ReactNode;
}) {
  if (faixas.length === 0) {
    return (
      <p className="flex h-48 items-center justify-center font-body-sm text-body-sm text-outline">
        Nenhuma partida no recorte.
      </p>
    );
  }

  const total = faixas.reduce((soma, faixa) => soma + faixa.valor, 0);
  const maximo = Math.max(...faixas.map((f) => f.valor), 1);
  const indiceModal = faixas.findIndex((f) => f.valor === maximo);

  const percentual = (valor: number) =>
    total ? `${Math.round((valor / total) * 100)}%` : "0%";

  return (
    <div>
      <div className="flex h-48 items-end gap-space-xs pt-7">
        {faixas.map((faixa, indice) => {
          const modal = indice === indiceModal;
          const altura = (faixa.valor / maximo) * 100;

          return (
            <div
              key={faixa.rotulo}
              className="group relative flex h-full flex-1 flex-col items-center justify-end gap-space-xs"
              title={`${faixa.rotulo}: ${formatarValor(faixa.valor)}`}
            >
              {modal && (
                <div className="absolute -top-7 flex items-center gap-space-xxs rounded bg-primary-container px-space-xs py-space-xxs font-badge-status text-badge-status text-on-primary-container shadow-lg">
                  <span
                    className="h-1.5 w-1.5 animate-ping rounded-full bg-on-primary-container"
                    aria-hidden
                  />
                  {percentual(faixa.valor)} MODAL
                </div>
              )}

              <span
                className={`font-label-caps text-label-caps transition-colors ${
                  modal
                    ? "font-bold text-primary"
                    : "text-outline group-hover:text-primary"
                }`}
              >
                {percentual(faixa.valor)}
              </span>

              <div
                className={`w-full rounded-t transition-all ${
                  modal
                    ? "bg-gradient-to-t from-secondary to-primary-container shadow-[0_0_12px_rgba(0,229,255,0.35)]"
                    : "bg-surface-container-highest group-hover:bg-secondary-container"
                }`}
                // 2% de piso: uma faixa com uma partida so precisa continuar
                // visivel, senao a coluna some e a faixa parece nao existir.
                style={{ height: `${Math.max(2, altura)}%` }}
              />
            </div>
          );
        })}
      </div>

      <div className="mt-space-xs flex gap-space-xs border-t border-outline-variant/30 pt-space-xs">
        {faixas.map((faixa) => (
          <span
            key={faixa.rotulo}
            className="flex-1 text-center font-label-caps text-label-caps text-outline"
          >
            {faixa.rotulo}
          </span>
        ))}
      </div>

      {(rodapeEsquerda || rodapeDireita) && (
        <div className="mt-space-md flex items-center justify-between border-t border-outline-variant/30 pt-space-sm text-outline">
          <span className="font-body-sm text-body-sm">{rodapeEsquerda}</span>
          <span className="font-title-code text-title-code text-primary">
            {rodapeDireita}
          </span>
        </div>
      )}
    </div>
  );
}
