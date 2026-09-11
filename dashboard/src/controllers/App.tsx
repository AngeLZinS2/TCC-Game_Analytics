import { Navigate, Route, Routes, useParams, useSearchParams } from "react-router-dom";

import { BarraSuperior } from "@views/layout/BarraSuperior";
import { NavInferior } from "@views/layout/NavInferior";
import { TrilhoLateral } from "@views/layout/TrilhoLateral";
import { ProvedorJogo } from "@views/layout/JogoAtual";
import { VisaoGeralPagina } from "./paginas/VisaoGeral";
import { CatalogoLayout } from "./paginas/catalogo/CatalogoLayout";
import { JogoSteamPagina } from "./paginas/JogoSteam";
import { JogoXboxPagina } from "./paginas/JogoXbox";
import { HeroiDetalhePagina } from "./paginas/HeroiDetalhe";
import { PartidaPagina } from "./paginas/Partida";
import { RecomendacoesReviewsPagina } from "./paginas/RecomendacoesReviews";
import { AssistenteIAPagina } from "./paginas/AssistenteIA";
import { EsportsLayout } from "./paginas/esports/EsportsLayout";
import { AdminPagina } from "./paginas/admin/AdminPagina";
import { useTelemetriaAcesso } from "@models/hooks/telemetria";

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
  useTelemetriaAcesso();

  return (
    <ProvedorJogo>
      {/* `overflow-x-clip`: rede de segurança contra um SVG decorativo ou um
          número grande que vaze uns pixels e cause rolagem lateral no celular.
          Não afeta os contêineres de tabela, que rolam por conta própria. */}
      <div className="min-h-screen overflow-x-clip bg-background font-body-md text-body-md text-on-surface antialiased selection:bg-primary-container selection:text-on-primary-container">
        {/* Trilho lateral (lg+); barra superior e nav inferior cobrem o resto. */}
        <TrilhoLateral />
        <BarraSuperior />

        {/* pt-16 abre espaco para a barra superior fixa; o pb extra no mobile
            abre espaco para a NavInferior (que não existe no desktop); lg:pl-60
            abre espaco para o trilho lateral. */}
        <main className="space-y-space-xl px-space-base pb-[calc(3.5rem+env(safe-area-inset-bottom)+1rem)] pt-[calc(4rem+1.25rem)] sm:px-space-lg md:pb-space-3xl md:pt-[calc(4rem+1.5rem)] lg:pl-[calc(15rem+1.25rem)]">
          <Routes>
            <Route path="/" element={<VisaoGeralPagina />} />

            {/* Catálogo de Jogos: a loja é o segmento da rota; as telas de
                detalhe continuam soltas, fora das abas. `/steam` redireciona
                (não quebra a landing `/mobile.html` nem links salvos). */}
            <Route
              path="/catalogo"
              element={<Navigate to="/catalogo/steam" replace />}
            />
            <Route path="/catalogo/:loja" element={<CatalogoLayout />} />
            <Route path="/steam" element={<Navigate to="/catalogo/steam" replace />} />
            <Route path="/steam/:appId" element={<JogoSteamPagina />} />
            <Route path="/xbox/:productId" element={<JogoXboxPagina />} />

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
            <Route path="/admin" element={<AdminPagina />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        <NavInferior />
      </div>
    </ProvedorJogo>
  );
}
