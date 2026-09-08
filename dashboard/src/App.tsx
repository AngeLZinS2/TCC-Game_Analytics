import { Navigate, Route, Routes, useParams, useSearchParams } from "react-router-dom";

import { BarraSuperior } from "./layout/BarraSuperior";
import { NavInferior } from "./layout/NavInferior";
import { ProvedorJogo } from "./layout/JogoAtual";
import { VisaoGeralPagina } from "./paginas/VisaoGeral";
import { SteamPagina } from "./paginas/Steam";
import { JogoSteamPagina } from "./paginas/JogoSteam";
import { HeroiDetalhePagina } from "./paginas/HeroiDetalhe";
import { PartidaPagina } from "./paginas/Partida";
import { RecomendacoesReviewsPagina } from "./paginas/RecomendacoesReviews";
import { AssistenteIAPagina } from "./paginas/AssistenteIA";
import { EsportsLayout } from "./paginas/esports/EsportsLayout";

/**
 * Rotas antigas (`/partidas`, `/previsao`, `/herois`, `/jogadores`) viraram
 * sub-abas de E-Sports. Este redirect preserva o `?jogo=` de um link colado
 * antes da mudanca, jogando-o no primeiro segmento da rota nova.
 */
function RedirecionaEsports({ aba }: { aba: string }) {
  const [parametros] = useSearchParams();
  const jogo = parametros.get("jogo") ?? "dota2";
  return <Navigate to={`/esports/${jogo}/${aba}`} replace />;
}

/** `/esports` sem jogo cai no padrao; com jogo mas sem aba, na primeira aba. */
function EsportsSemAba() {
  const { jogo } = useParams();
  return <Navigate to={`/esports/${jogo ?? "dota2"}/partidas`} replace />;
}

export function App() {
  return (
    <ProvedorJogo>
      {/* `overflow-x-clip`: rede de segurança contra um SVG decorativo ou um
          número grande que vaze uns pixels e cause rolagem lateral no celular.
          Não afeta os contêineres de tabela, que rolam por conta própria. */}
      <div className="min-h-screen overflow-x-clip bg-background font-body-md text-body-md text-on-surface antialiased selection:bg-primary-container selection:text-on-primary-container">
        <BarraSuperior />

        {/* pt-16 abre espaco para a barra superior fixa; o pb extra no mobile
            abre espaco para a NavInferior (que não existe no desktop). */}
        <main className="space-y-space-xl px-space-base pb-[calc(3.5rem+env(safe-area-inset-bottom)+1rem)] pt-[calc(4rem+1.25rem)] sm:px-space-lg md:pb-space-3xl md:pt-[calc(4rem+1.5rem)]">
          <Routes>
            <Route path="/" element={<VisaoGeralPagina />} />
            <Route path="/steam" element={<SteamPagina />} />
            <Route path="/steam/:appId" element={<JogoSteamPagina />} />

            {/* Area E-Sports: jogo no 1o segmento, sub-aba no 2o. */}
            <Route path="/esports" element={<EsportsSemAba />} />
            <Route path="/esports/:jogo" element={<EsportsSemAba />} />
            <Route path="/esports/:jogo/:aba" element={<EsportsLayout />} />

            {/* Telas de detalhe: continuam fora das abas. */}
            <Route path="/partidas/:idPartida" element={<PartidaPagina />} />
            <Route path="/herois/:idPersonagem" element={<HeroiDetalhePagina />} />

            {/* Rotas antigas -> abas de E-Sports. */}
            <Route path="/partidas" element={<RedirecionaEsports aba="partidas" />} />
            <Route path="/previsao" element={<RedirecionaEsports aba="previsao" />} />
            <Route path="/herois" element={<RedirecionaEsports aba="herois" />} />
            <Route path="/jogadores" element={<RedirecionaEsports aba="jogadores" />} />

            <Route path="/recomendacoes" element={<RecomendacoesReviewsPagina />} />
            <Route path="/assistente" element={<AssistenteIAPagina />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        <NavInferior />
      </div>
    </ProvedorJogo>
  );
}
