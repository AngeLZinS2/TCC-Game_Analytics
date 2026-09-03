import { Navigate, Route, Routes } from "react-router-dom";

import { BarraLateral } from "./layout/BarraLateral";
import { BarraSuperior } from "./layout/BarraSuperior";
import { ProvedorJogo } from "./layout/JogoAtual";
import { VisaoGeralPagina } from "./paginas/VisaoGeral";
import { SteamPagina } from "./paginas/Steam";
import { JogoSteamPagina } from "./paginas/JogoSteam";
import { HeroisPagina } from "./paginas/Herois";
import { JogadoresPagina } from "./paginas/Jogadores";
import { PartidasPagina } from "./paginas/Partidas";
import { PartidaPagina } from "./paginas/Partida";
import { PrevisaoConfrontoPagina } from "./paginas/PrevisaoConfronto";
import { RecomendacoesReviewsPagina } from "./paginas/RecomendacoesReviews";
import { AssistenteIAPagina } from "./paginas/AssistenteIA";

export function App() {
  return (
    <ProvedorJogo>
      <div className="min-h-screen bg-background font-body-md text-body-md text-on-surface antialiased selection:bg-primary-container selection:text-on-primary-container">
        <BarraLateral />
        <BarraSuperior />

        {/* pl-72 abre espaco para a lateral fixa; pt-16 para a barra superior. */}
        <main className="space-y-space-xl px-space-lg pb-space-3xl pl-[calc(18rem+1.5rem)] pr-space-lg pt-[calc(4rem+1.5rem)]">
          <Routes>
            <Route path="/" element={<VisaoGeralPagina />} />
            <Route path="/steam" element={<SteamPagina />} />
            <Route path="/steam/:appId" element={<JogoSteamPagina />} />
            <Route path="/partidas" element={<PartidasPagina />} />
            <Route path="/partidas/:idPartida" element={<PartidaPagina />} />
            <Route path="/herois" element={<HeroisPagina />} />
            <Route path="/jogadores" element={<JogadoresPagina />} />
            <Route path="/previsao" element={<PrevisaoConfrontoPagina />} />
            <Route path="/recomendacoes" element={<RecomendacoesReviewsPagina />} />
            <Route path="/assistente" element={<AssistenteIAPagina />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </ProvedorJogo>
  );
}
