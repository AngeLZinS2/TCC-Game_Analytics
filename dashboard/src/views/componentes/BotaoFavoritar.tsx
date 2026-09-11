/**
 * Estrela/coração de favoritar - jogo ou time, mesma peça.
 *
 * Favoritar é dado de conta (Fase 32), mas o botão aparece em telas
 * públicas (ficha do jogo, previsão de confronto). Sem sessão, o clique não
 * falha silenciosamente nem abre um modal de login à parte - manda pra
 * `/perfil`, que já é a tela que sabe pedir login (`RotaProtegida`).
 */

import { useNavigate } from "react-router-dom";

import { useUsuario } from "@models/conta/contexto";
import { Icone } from "./base";

const TAMANHOS = {
  md: { caixa: "h-9 w-9", icone: "text-[18px]" },
  sm: { caixa: "h-6 w-6", icone: "text-[14px]" },
} as const;

export function BotaoFavoritar({
  favoritado,
  aoAlternar,
  ocupado = false,
  rotulo = "Favoritar",
  tamanho = "md",
}: {
  favoritado: boolean;
  aoAlternar: () => void;
  ocupado?: boolean;
  rotulo?: string;
  tamanho?: keyof typeof TAMANHOS;
}) {
  const { usuario } = useUsuario();
  const navegar = useNavigate();
  const medidas = TAMANHOS[tamanho];

  function clicar() {
    if (!usuario) {
      navegar("/perfil");
      return;
    }
    aoAlternar();
  }

  return (
    <button
      type="button"
      onClick={clicar}
      disabled={ocupado}
      title={usuario ? (favoritado ? "Remover dos favoritos" : rotulo) : "Entre para favoritar"}
      aria-pressed={favoritado}
      className={`inline-flex shrink-0 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${medidas.caixa} ${
        favoritado
          ? "bg-error/10 text-error hover:bg-error/20"
          : "bg-surface-container text-outline hover:bg-surface-container-high hover:text-on-surface"
      }`}
    >
      <Icone nome={favoritado ? "favorite" : "favorite_border"} className={medidas.icone} />
    </button>
  );
}
