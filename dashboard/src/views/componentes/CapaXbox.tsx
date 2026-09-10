/**
 * A capa de um jogo da Xbox Store.
 *
 * Diferente da `CapaJogo` da Steam: la a URL sai deterministicamente do
 * `app_id`; aqui a Microsoft nao publica caminho previsivel, entao a imagem
 * SEMPRE vem do coletor (`imagem_capa` / `imagem_header`). Sem URL, ou quando
 * ela falha, o lugar dela e ocupado pela inicial do jogo - o mesmo bloco de
 * 48px que a `CapaJogo` reserva, para nao desalinhar a linha da tabela.
 */

import { useState } from "react";

export function CapaXbox({
  nome,
  imagemUrl,
  className = "h-12 w-12",
}: {
  nome: string;
  imagemUrl?: string | null;
  className?: string;
}) {
  const [falhou, setFalhou] = useState(false);

  if (falhou || !imagemUrl) {
    return (
      <div
        className={`flex shrink-0 items-center justify-center rounded bg-surface-container-high font-headline-md text-headline-md text-outline ${className}`}
        aria-hidden
      >
        {nome.charAt(0).toUpperCase()}
      </div>
    );
  }

  return (
    <img
      src={imagemUrl}
      alt=""
      loading="lazy"
      onError={() => setFalhou(true)}
      className={`shrink-0 rounded bg-surface-container object-cover shadow-md ${className}`}
    />
  );
}
