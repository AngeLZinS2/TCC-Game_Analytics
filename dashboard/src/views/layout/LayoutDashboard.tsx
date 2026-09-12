/**
 * A casca do painel: trilho lateral, barra superior, nav inferior e o `<main>`
 * que reserva espaço para os três.
 *
 * Existe separado do `App.tsx` porque a Home (`/`) parou de usar essa casca -
 * ela é a landing cinematográfica, tela cheia, sem nada de navegação de
 * instrumento. Toda rota que É o painel entra como filha de
 * `<Route element={<LayoutDashboard />}>`, e o `<Outlet />` é onde ela
 * desenha.
 */

import { Outlet } from "react-router-dom";

import { BarraSuperior } from "./BarraSuperior";
import { NavInferior } from "./NavInferior";
import { TrilhoLateral } from "./TrilhoLateral";

export function LayoutDashboard() {
  return (
    // `overflow-x-clip`: rede de segurança contra um SVG decorativo ou um
    // número grande que vaze uns pixels e cause rolagem lateral no celular.
    // Não afeta os contêineres de tabela, que rolam por conta própria.
    <div className="min-h-screen overflow-x-clip bg-background font-body-md text-body-md text-on-surface antialiased selection:bg-primary-container selection:text-on-primary-container">
      {/* Trilho lateral (lg+); barra superior e nav inferior cobrem o resto. */}
      <TrilhoLateral />
      <BarraSuperior />

      {/* pt-16 abre espaco para a barra superior fixa; o pb extra no mobile
          abre espaco para a NavInferior (que não existe no desktop); lg:pl-60
          abre espaco para o trilho lateral. */}
      <main className="space-y-space-xl px-space-base pb-[calc(3.5rem+env(safe-area-inset-bottom)+1rem)] pt-[calc(4rem+1.25rem)] sm:px-space-lg md:pb-space-3xl md:pt-[calc(4rem+1.5rem)] lg:pl-[calc(15rem+1.25rem)]">
        <Outlet />
      </main>

      <NavInferior />
    </div>
  );
}
