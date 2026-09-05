/**
 * O carrossel do topo da ficha: um slot só, que se troca sozinho.
 *
 * A regra de avanço depende do que está na tela, e é essa a razão de o
 * componente existir em vez de um `setInterval` genérico:
 *
 * * **Imagem** troca por tempo (`SEGUNDOS_POR_IMAGEM`).
 * * **Vídeo** toca até o fim e só então passa - cortar um trailer no meio para
 *   cumprir um cronômetro seria pior que não ter vídeo nenhum.
 *
 * Sempre mudo (`muted`), e não é só decisão de gosto: navegador nenhum deixa
 * um vídeo com som começar sozinho, então autoplay com áudio simplesmente não
 * tocaria. Quem quiser som tem o controle de volume no player.
 *
 * **Por que `hls.js`.** A Steam parou de publicar mp4/webm: o `appdetails` hoje
 * traz só DASH e HLS, e o Chrome não toca nenhum dos dois nativamente (o
 * Safari toca HLS). É protocolo de streaming, não algo que se escreve à mão -
 * daí a única dependência de player do projeto. O CDN da Valve responde com
 * `Access-Control-Allow-Origin: *`, então o download dos segmentos funciona
 * direto do navegador, sem proxy nosso no meio.
 */

import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";

import type { MidiaJogo } from "../api/tipos";
import { Icone } from "./base";

/** Quanto uma captura de tela fica antes de passar para a próxima. */
const SEGUNDOS_POR_IMAGEM = 6;

/**
 * O player de um item de vídeo. Monta o `hls.js` no `<video>` e avisa quando o
 * trailer acaba - é o `onFim` que faz o carrossel andar.
 *
 * Fica em componente próprio de propósito: assim cada troca de mídia monta um
 * `<video>` novo, e o `useEffect` de limpeza destrói a instância do `hls.js`
 * junto. Reaproveitar um player só entre trocas vazaria buffer de vídeo.
 */
function Video({ midia, onFim }: { midia: MidiaJogo; onFim: () => void }) {
  const referencia = useRef<HTMLVideoElement>(null);
  const [falhou, setFalhou] = useState(false);

  useEffect(() => {
    const elemento = referencia.current;
    if (!elemento) return;

    // `Hls.isSupported()` vem PRIMEIRO, e não é detalhe: o Chrome responde
    // "maybe" para `canPlayType("application/vnd.apple.mpegurl")` mesmo sem
    // saber tocar HLS. Testar o `canPlayType` antes cai no caminho nativo, o
    // vídeo nunca carrega (`readyState` fica em 0) e não sai erro nenhum no
    // console. Só o Safari, que realmente toca, fica com o caminho nativo.
    if (!Hls.isSupported()) {
      if (elemento.canPlayType("application/vnd.apple.mpegurl")) {
        elemento.src = midia.url;
      } else {
        setFalhou(true);
      }
      return;
    }

    const hls = new Hls({ autoStartLoad: true });
    hls.loadSource(midia.url);
    hls.attachMedia(elemento);
    hls.on(Hls.Events.ERROR, (_evento, dado) => {
      // Só o erro fatal derruba: o hls.js se recupera sozinho dos demais.
      if (dado.fatal) setFalhou(true);
    });

    return () => hls.destroy();
  }, [midia.url]);

  // Sem player possível, o cartaz do trailer ainda serve de imagem - e o
  // carrossel continua andando pelo tempo, como faria com uma captura.
  useEffect(() => {
    if (!falhou) return;
    const relogio = setTimeout(onFim, SEGUNDOS_POR_IMAGEM * 1000);
    return () => clearTimeout(relogio);
  }, [falhou, onFim]);

  if (falhou) {
    return (
      <img src={midia.cartaz} alt="" className="h-full w-full object-cover" />
    );
  }

  return (
    <video
      ref={referencia}
      poster={midia.cartaz || undefined}
      autoPlay
      muted
      playsInline
      controls
      onEnded={onFim}
      onError={() => setFalhou(true)}
      className="h-full w-full bg-black object-cover"
    />
  );
}

export function CarrosselMidia({
  midias,
  className = "",
}: {
  midias: MidiaJogo[];
  className?: string;
}) {
  const [indice, setIndice] = useState(0);

  // Volta pro começo quando a lista muda (navegar de um jogo para outro).
  useEffect(() => {
    setIndice(0);
  }, [midias]);

  const atual = midias[indice];

  // A imagem avança por tempo; o vídeo, no `onEnded` (ver `Video`).
  useEffect(() => {
    if (!atual || atual.tipo === "video" || midias.length < 2) return;
    const relogio = setTimeout(
      () => setIndice((i) => (i + 1) % midias.length),
      SEGUNDOS_POR_IMAGEM * 1000,
    );
    return () => clearTimeout(relogio);
  }, [atual, indice, midias.length]);

  if (!atual) return null;

  function avancar() {
    setIndice((i) => (i + 1) % midias.length);
  }

  return (
    <div className={`overflow-hidden rounded-xl bg-black/60 ${className}`}>
      <div className="relative aspect-video w-full">
        {atual.tipo === "video" ? (
          <Video key={atual.url} midia={atual} onFim={avancar} />
        ) : (
          <img
            key={atual.url}
            src={atual.url}
            alt=""
            className="h-full w-full object-cover"
          />
        )}

        {atual.tipo === "video" && atual.titulo && (
          <span className="pointer-events-none absolute left-space-sm top-space-sm inline-flex items-center gap-space-xxs rounded bg-black/70 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-on-surface backdrop-blur-sm">
            <Icone nome="play_circle" className="text-[13px] text-primary" />
            {atual.titulo}
          </span>
        )}
      </div>

      {/* Marcadores: também servem de atalho para pular direto num item. */}
      {midias.length > 1 && (
        <div className="flex items-center justify-center gap-space-xxs bg-surface-container-lowest px-space-sm py-space-xs">
          {midias.map((midia, i) => (
            <button
              key={midia.url}
              type="button"
              onClick={() => setIndice(i)}
              aria-label={`Ir para a mídia ${i + 1} de ${midias.length}`}
              aria-current={i === indice}
              className={`h-1.5 rounded-full transition-all ${
                i === indice
                  ? "w-6 bg-primary"
                  : "w-1.5 bg-outline/50 hover:bg-outline"
              }`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
