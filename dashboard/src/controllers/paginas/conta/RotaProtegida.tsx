/**
 * Envelope de rota que exige conta: "Perfil" e "Assistente de IA" (Fase 31).
 * Enquanto o Firebase confirma a sessao guardada, mostra um esqueleto em vez
 * de piscar a tela de login pra quem ja estava logado.
 */

import type { ReactNode } from "react";

import { useUsuario } from "@models/conta/contexto";
import { Esqueleto } from "@views/componentes/base";
import { EntrarOuCriarConta } from "./EntrarOuCriarConta";

export function RotaProtegida({
  children,
  descricao,
}: {
  children: ReactNode;
  /** Mensagem da tela de login, especifica da rota (ex.: "para usar o Assistente de IA"). */
  descricao?: string;
}) {
  const { usuario, carregando } = useUsuario();

  if (carregando) return <Esqueleto altura={320} />;
  if (!usuario) return <EntrarOuCriarConta descricao={descricao} />;
  return <>{children}</>;
}
