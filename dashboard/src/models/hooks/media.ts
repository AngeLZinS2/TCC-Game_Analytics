/**
 * `useEhMobile` — `true` abaixo do breakpoint `sm` do Tailwind (640px), a
 * "visão de celular".
 *
 * O resto da responsividade do PlayDB é 100% CSS (breakpoints do Tailwind);
 * este hook existe só para as poucas decisões que o CSS não resolve — a
 * primeira é o padrão de "itens por página" da paginação, que no celular
 * começa em 5 para enxugar a tela.
 *
 * O estado inicial já lê `matchMedia` de forma síncrona, então no navegador o
 * primeiro render já vem com o valor certo (sem piscar de desktop pra mobile).
 * Fora do navegador (teste, thumbnail) cai em `false`.
 */

import { useEffect, useState } from "react";

const CONSULTA = "(max-width: 639px)";

function medir(): boolean {
  try {
    return window.matchMedia(CONSULTA).matches;
  } catch {
    return false;
  }
}

export function useEhMobile(): boolean {
  const [ehMobile, setEhMobile] = useState(medir);

  useEffect(() => {
    let mq: MediaQueryList;
    try {
      mq = window.matchMedia(CONSULTA);
    } catch {
      return;
    }
    const aoMudar = () => setEhMobile(mq.matches);
    aoMudar();
    mq.addEventListener("change", aoMudar);
    return () => mq.removeEventListener("change", aoMudar);
  }, []);

  return ehMobile;
}
