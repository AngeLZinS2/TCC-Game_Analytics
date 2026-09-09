/**
 * Primitivas de animacao para grafico e metrica - crescer, desenhar, contar.
 *
 * Nada daqui usa uma biblioteca de animacao. O padrao do projeto e CSS
 * (`transition`) sobre um valor que o React controla, e o problema que essas
 * duas funcoes resolvem e sempre o mesmo: uma transicao CSS so anima quando a
 * propriedade MUDA depois da primeira pintura - se o elemento ja nasce com o
 * valor final (que era o que toda barra/numero deste projeto fazia ate aqui),
 * nao ha "de onde" para a transicao vir, e o resultado e o valor aparecendo
 * pronto, sem crescer.
 *
 * `useEntrarNaTela` da esse "de onde": renderiza no estado zero por um
 * instante e so depois libera o valor real, com o CSS cuidando do meio do
 * caminho. `useContagem` faz o analogo pra numero, sem depender de CSS -
 * anima o proprio valor via `requestAnimationFrame`.
 *
 * As duas ignoram `prefers-reduced-motion` de proposito: a animacao e parte
 * da identidade visual do painel (e da demonstracao da TCC), entao toca
 * sempre, independente da preferencia de acessibilidade do sistema.
 */

import { useEffect, useRef, useState } from "react";

/**
 * `false` no primeiro paint, `true` a partir do paint seguinte - a janela que
 * uma transicao CSS precisa pra animar "de 0 ate o valor" em vez de nascer
 * pronta. Rearma sempre que `chave` muda (troca de periodo, nova pagina de
 * dado, refetch): a barra/linha volta a crescer do zero em vez de saltar.
 */
export function useEntrarNaTela(chave?: unknown): boolean {
  const [entrou, setEntrou] = useState(false);
  const quadro = useRef<number | undefined>(undefined);

  useEffect(() => {
    setEntrou(false);
    // Duplo requestAnimationFrame: o primeiro garante que o navegador ja
    // pintou o estado zero: so no segundo e seguro liberar o valor final sem
    // o browser fundir os dois quadros num so (o que pareceria "sem animacao").
    const primeiro = requestAnimationFrame(() => {
      quadro.current = requestAnimationFrame(() => setEntrou(true));
    });
    return () => {
      cancelAnimationFrame(primeiro);
      if (quadro.current) cancelAnimationFrame(quadro.current);
    };
    // `chave` de proposito so no gatilho de rearme - o efeito nao le nada
    // dela, so reagenda a entrada quando ela muda.
  }, [chave]);

  return entrou;
}

/**
 * Anima um numero do valor anterior ate `valorFinal`, com desaceleracao no
 * fim (a mesma curva que todo indicador digital usa - contar linear ate o
 * ultimo instante pareceria mecanico). `null`/`undefined` passa direto, sem
 * tentar animar "sem dado".
 */
export function useContagem(
  valorFinal: number | null | undefined,
  duracaoMs = 900,
): number | null {
  const [exibido, setExibido] = useState(valorFinal ?? 0);
  const anterior = useRef(valorFinal ?? 0);

  useEffect(() => {
    if (valorFinal === null || valorFinal === undefined || !Number.isFinite(valorFinal)) {
      return;
    }

    const inicio = anterior.current;
    const alvo = valorFinal;
    if (inicio === alvo) {
      setExibido(alvo);
      return;
    }

    const t0 = performance.now();
    let quadro: number;

    const passo = (agora: number) => {
      const progresso = Math.min(1, (agora - t0) / duracaoMs);
      // Ease-out cubico: rapido no comeco, assenta no fim - como um contador
      // digital "freando" no numero certo, nao um metronomo linear.
      const suavizado = 1 - (1 - progresso) ** 3;
      setExibido(inicio + (alvo - inicio) * suavizado);
      if (progresso < 1) {
        quadro = requestAnimationFrame(passo);
      } else {
        anterior.current = alvo;
      }
    };

    quadro = requestAnimationFrame(passo);
    return () => cancelAnimationFrame(quadro);
  }, [valorFinal, duracaoMs]);

  return valorFinal === null || valorFinal === undefined ? null : exibido;
}
