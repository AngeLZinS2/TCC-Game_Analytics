/**
 * Sobreposicao modal no idioma do HUD.
 *
 * Fecha por Escape e por clique no fundo - as duas saidas que alguem tenta
 * antes de procurar o botao. Enquanto esta aberta, o corpo da pagina para de
 * rolar: sem isso a roda do mouse rola a pagina atras do modal, e o conteudo
 * que se estava lendo some do lugar.
 */

import { useEffect, type ReactNode } from "react";

import { Icone } from "./base";

export function Modal({
  aberto,
  titulo,
  descricao,
  aoFechar,
  children,
}: {
  aberto: boolean;
  titulo: ReactNode;
  descricao?: ReactNode;
  aoFechar: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!aberto) return;

    function aoTeclar(evento: KeyboardEvent) {
      if (evento.key === "Escape") aoFechar();
    }

    const rolagemAnterior = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", aoTeclar);

    return () => {
      document.body.style.overflow = rolagemAnterior;
      window.removeEventListener("keydown", aoTeclar);
    };
  }, [aberto, aoFechar]);

  if (!aberto) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto bg-background/80 p-space-lg backdrop-blur-sm"
      role="dialog"
      aria-modal
      aria-label={typeof titulo === "string" ? titulo : undefined}
      onClick={aoFechar}
    >
      <div
        className="my-space-xl w-full max-w-5xl space-y-space-md rounded-xl bg-surface-container-low p-space-lg shadow-2xl"
        // O clique dentro nao pode fechar: so o do fundo.
        onClick={(evento) => evento.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-space-base border-b border-outline-variant/40 pb-space-md">
          <div className="min-w-0">
            <h2 className="font-headline-md text-headline-md uppercase tracking-wide text-on-surface">
              {titulo}
            </h2>
            {descricao && (
              <p className="mt-space-xxs font-body-sm text-body-sm text-outline">
                {descricao}
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={aoFechar}
            aria-label="Fechar"
            className="shrink-0 rounded bg-surface-container p-space-xs text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface"
          >
            <Icone nome="close" className="text-[20px]" />
          </button>
        </div>

        {children}
      </div>
    </div>
  );
}
