/**
 * Paralaxe de mouse pra Home: o cursor move, as camadas do herói se deslocam
 * em velocidades diferentes - a pista de profundidade que substitui uma cena
 * 3D de verdade.
 *
 * Escreve direto no DOM (`--mx`/`--my` como CSS custom properties no
 * container) em vez de `useState`, no mesmo espírito de
 * `models/hooks/animacao.ts`: um `pointermove` dispara a 60-120hz, e um
 * `setState` a essa taxa re-renderizaria a árvore inteira da Home a cada
 * pixel de movimento do mouse por nada - o React não precisa saber a
 * posição do cursor, só o CSS precisa.
 *
 * Os filhos leem a variável em `style` inline:
 * `transform: "translate3d(calc(var(--mx, 0) * 24px), calc(var(--my, 0) * 18px), 0)"` -
 * o multiplicador de cada filho é a profundidade dele.
 */

import { useEffect, useRef, type RefObject } from "react";

export function useParalaxeMouse<T extends HTMLElement>(): RefObject<T | null> {
  const raiz = useRef<T>(null);

  useEffect(() => {
    const alvo = raiz.current;
    if (!alvo) return;

    let quadro: number | undefined;
    let mx = 0;
    let my = 0;

    function aoMoverPonteiro(evento: PointerEvent) {
      const retangulo = alvo!.getBoundingClientRect();
      // -1..1 em volta do centro do container, não da janela inteira - o
      // efeito fica ligado à área do herói, mesmo com a página rolada.
      mx = ((evento.clientX - retangulo.left) / retangulo.width) * 2 - 1;
      my = ((evento.clientY - retangulo.top) / retangulo.height) * 2 - 1;

      if (quadro === undefined) {
        quadro = requestAnimationFrame(() => {
          alvo!.style.setProperty("--mx", mx.toFixed(3));
          alvo!.style.setProperty("--my", my.toFixed(3));
          quadro = undefined;
        });
      }
    }

    // Sai do container: as camadas voltam ao centro em vez de ficarem presas
    // no último canto que o cursor tocou antes de ir embora.
    function aoSair() {
      alvo!.style.setProperty("--mx", "0");
      alvo!.style.setProperty("--my", "0");
    }

    alvo.addEventListener("pointermove", aoMoverPonteiro);
    alvo.addEventListener("pointerleave", aoSair);
    return () => {
      alvo.removeEventListener("pointermove", aoMoverPonteiro);
      alvo.removeEventListener("pointerleave", aoSair);
      if (quadro !== undefined) cancelAnimationFrame(quadro);
    };
  }, []);

  return raiz;
}
