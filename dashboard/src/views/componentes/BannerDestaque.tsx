/**
 * O banner de destaque no topo de Ofertas e Catálogo: uma faixa larga com o
 * título da seção à esquerda e, ao fundo, a arte dos próprios jogos listados
 * logo abaixo — em vez de uma ilustração fixa, sem relação com o que a tela
 * mostra.
 *
 * Troca de imagem por tempo (mesmo padrão do `CarrosselMidia`, só que aqui
 * é sempre imagem — nunca vídeo — e o avanço é automático, sem marcadores:
 * é decoração de fundo, não um conteúdo que alguém navega).
 */

import { useEffect, useState } from "react";

const SEGUNDOS_POR_IMAGEM = 6;

export function BannerDestaque({
  imagens,
  className = "",
  children,
}: {
  /** URLs de capa/header dos jogos — a mesma lista da tela logo abaixo. */
  imagens: string[];
  className?: string;
  children: React.ReactNode;
}) {
  const [indice, setIndice] = useState(0);

  useEffect(() => {
    setIndice(0);
  }, [imagens.length]);

  useEffect(() => {
    if (imagens.length < 2) return;
    const relogio = setInterval(
      () => setIndice((i) => (i + 1) % imagens.length),
      SEGUNDOS_POR_IMAGEM * 1000,
    );
    return () => clearInterval(relogio);
  }, [imagens.length]);

  return (
    <div
      className={`relative isolate overflow-hidden rounded-xl bg-surface-container-lowest ${className}`}
    >
      {imagens.map((url, i) => (
        <img
          key={url}
          src={url}
          alt=""
          aria-hidden
          loading={i === 0 ? "eager" : "lazy"}
          className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-1000 motion-reduce:transition-none ${
            i === indice ? "opacity-100" : "opacity-0"
          }`}
        />
      ))}

      {/* Legibilidade do texto sobre a arte - forte à esquerda (onde o
          conteúdo mora), esmaecendo pra deixar a arte aparecer à direita. */}
      <div className="absolute inset-0 bg-gradient-to-r from-surface-container-lowest via-surface-container-lowest/85 to-surface-container-lowest/10" />
      <div className="absolute inset-0 bg-gradient-to-t from-surface-container-lowest/60 via-transparent to-transparent" />

      <div className="relative flex min-h-[13rem] flex-col justify-center gap-space-sm px-space-lg py-space-lg sm:min-h-[15rem]">
        {children}
      </div>
    </div>
  );
}
