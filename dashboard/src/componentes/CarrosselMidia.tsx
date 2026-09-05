/**
 * A galeria da loja no cabeçalho da ficha: um slot só, que se troca sozinho.
 *
 * A regra de avanço depende do que está na tela, e é essa a razão de o
 * componente existir em vez de um `setInterval` genérico:
 *
 * * **Imagem** troca por tempo (`SEGUNDOS_POR_IMAGEM`).
 * * **Vídeo** toca até o fim e só então passa - cortar um trailer no meio para
 *   cumprir um cronômetro seria pior que não ter vídeo nenhum.
 *
 * Começa sempre mudo, e não é só decisão de gosto: navegador nenhum deixa um
 * vídeo com som começar sozinho, então autoplay com áudio simplesmente não
 * tocaria. O botão de som fica no canto, e a escolha de quem clicou sobrevive
 * à troca de trailer (por isso o estado mora aqui, não dentro do `Video`).
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
 *
 * Sem `controls`: a barra nativa do Chrome (play, tempo, tela cheia, menu) é
 * alta demais e destoa do resto do painel num bloco deste tamanho. O que ela
 * tinha de útil aqui virou gesto - clicar alterna pausa - e o botão de som,
 * que é o único controle que alguém realmente procura num trailer que já
 * começou sozinho.
 */
function Video({
  midia,
  mudo,
  onFim,
  onProgresso,
}: {
  midia: MidiaJogo;
  mudo: boolean;
  onFim: () => void;
  onProgresso: (fracao: number) => void;
}) {
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
    return <img src={midia.cartaz} alt="" className="h-full w-full object-cover" />;
  }

  return (
    <video
      ref={referencia}
      poster={midia.cartaz || undefined}
      autoPlay
      muted={mudo}
      playsInline
      onEnded={onFim}
      onError={() => setFalhou(true)}
      onTimeUpdate={(evento) => {
        const el = evento.currentTarget;
        if (el.duration) onProgresso(el.currentTime / el.duration);
      }}
      onClick={(evento) => {
        const el = evento.currentTarget;
        if (el.paused) void el.play();
        else el.pause();
      }}
      className="h-full w-full cursor-pointer bg-black object-cover"
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
  const [mudo, setMudo] = useState(true);
  const [progresso, setProgresso] = useState(0);

  // Volta pro começo quando a lista muda (navegar de um jogo para outro).
  useEffect(() => {
    setIndice(0);
  }, [midias]);

  const atual = midias[indice];
  const eVideo = atual?.tipo === "video";

  // A imagem avança por tempo; o vídeo, no `onEnded` (ver `Video`).
  useEffect(() => {
    setProgresso(0);
    if (!atual || eVideo || midias.length < 2) return;
    const relogio = setTimeout(
      () => setIndice((i) => (i + 1) % midias.length),
      SEGUNDOS_POR_IMAGEM * 1000,
    );
    return () => clearTimeout(relogio);
  }, [atual, eVideo, indice, midias.length]);

  if (!atual) return null;

  function avancar() {
    setIndice((i) => (i + 1) % midias.length);
  }

  return (
    <div
      className={`overflow-hidden rounded-xl bg-black shadow-lg ring-1 ring-outline-variant/25 ${className}`}
    >
      <div className="relative aspect-video w-full">
        {eVideo ? (
          <Video
            key={atual.url}
            midia={atual}
            mudo={mudo}
            onFim={avancar}
            onProgresso={setProgresso}
          />
        ) : (
          <img key={atual.url} src={atual.url} alt="" className="h-full w-full object-cover" />
        )}

        {eVideo && atual.titulo && (
          <span className="pointer-events-none absolute left-space-sm top-space-sm inline-flex max-w-[70%] items-center gap-space-xxs truncate rounded bg-black/60 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-on-surface backdrop-blur-sm">
            <Icone nome="play_circle" className="text-[13px] text-primary" />
            {atual.titulo}
          </span>
        )}

        {eVideo && (
          <button
            type="button"
            onClick={() => setMudo((m) => !m)}
            aria-label={mudo ? "Ativar som" : "Desativar som"}
            className="absolute right-space-sm top-space-sm flex h-7 w-7 items-center justify-center rounded bg-black/60 text-on-surface backdrop-blur-sm transition-colors hover:text-primary"
          >
            <Icone nome={mudo ? "volume_off" : "volume_up"} className="text-[15px]" />
          </button>
        )}

        {/* Marcadores sobre a mídia, não numa faixa embaixo: a faixa somava
            altura ao cabeçalho e se lia como um bloco solto. */}
        {midias.length > 1 && (
          <div className="absolute inset-x-0 bottom-0 flex items-end justify-center gap-space-xxs bg-gradient-to-t from-black/70 to-transparent px-space-sm pb-space-xs pt-space-lg">
            {midias.map((midia, i) => (
              <button
                key={midia.url}
                type="button"
                onClick={() => setIndice(i)}
                aria-label={`Ir para a mídia ${i + 1} de ${midias.length}`}
                aria-current={i === indice}
                className={`h-1 rounded-full transition-all ${
                  i === indice ? "w-5 bg-primary" : "w-1 bg-on-surface/40 hover:bg-on-surface/70"
                }`}
              />
            ))}
          </div>
        )}

        {/* Fio de progresso do trailer - substitui a barra nativa, que ocupava
            um oitavo da altura do bloco. */}
        {eVideo && (
          <div
            className="absolute inset-x-0 bottom-0 h-0.5 bg-primary/80 transition-[width] duration-200"
            style={{ width: `${Math.min(100, progresso * 100)}%` }}
            aria-hidden
          />
        )}
      </div>
    </div>
  );
}
