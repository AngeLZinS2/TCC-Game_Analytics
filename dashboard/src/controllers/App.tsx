import { Navigate, Route, Routes, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { LayoutDashboard } from "@views/layout/LayoutDashboard";
import { ProvedorJogo } from "@views/layout/JogoAtual";
import { HomePagina } from "./paginas/Home";
import { VisaoGeralPagina } from "./paginas/VisaoGeral";
import { CatalogoLayout } from "./paginas/catalogo/CatalogoLayout";
import { OfertasPagina } from "./paginas/Ofertas";
import { JogoSteamPagina } from "./paginas/JogoSteam";
import { JogoXboxPagina } from "./paginas/JogoXbox";
import { HeroiDetalhePagina } from "./paginas/HeroiDetalhe";
import { PartidaPagina } from "./paginas/Partida";
import { RecomendacoesReviewsPagina } from "./paginas/RecomendacoesReviews";
import { AssistenteIAPagina } from "./paginas/AssistenteIA";
import { PerfilPagina } from "./paginas/Perfil";
import { EsportsLayout } from "./paginas/esports/EsportsLayout";
import { AdminPagina } from "./paginas/admin/AdminPagina";
import { RotaProtegida } from "./paginas/conta/RotaProtegida";
import { ProvedorConta } from "@models/conta/contexto";
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
  const { t } = useTranslation();
  useTelemetriaAcesso();

  return (
    <ProvedorConta>
      <ProvedorJogo>
        <Routes>
          {/* A landing: tela cheia, sem casca de painel - é o que qualquer
              pessoa vê antes de entrar. Fora do `LayoutDashboard` de
              propósito (ver o comentário dele). */}
          <Route path="/" element={<HomePagina />} />

          <Route element={<LayoutDashboard />}>
            <Route path="/painel" element={<VisaoGeralPagina />} />

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
            <Route path="/ofertas" element={<OfertasPagina />} />
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

            {/* Exigem conta (Fase 31): a tela mostra login/cadastro no lugar
                do conteudo enquanto ninguem estiver logado. */}
            <Route
              path="/assistente"
              element={
                <RotaProtegida descricao={t("conta.rotaProtegida.assistente")}>
                  <AssistenteIAPagina />
                </RotaProtegida>
              }
            />
            <Route
              path="/perfil"
              element={
                <RotaProtegida descricao={t("conta.rotaProtegida.perfil")}>
                  <PerfilPagina />
                </RotaProtegida>
              }
            />

            {/* Login = a mesma conta do site; quem tem acesso é decidido pelo
                backend (ver AdminPagina.tsx). */}
            <Route
              path="/admin"
              element={
                <RotaProtegida descricao={t("conta.rotaProtegida.admin")}>
                  <AdminPagina />
                </RotaProtegida>
              }
            />
            {/* Rota quebrada -> o painel, não a landing: quem chegou aqui já
                estava usando o site, não é visita pela primeira vez. */}
            <Route path="*" element={<Navigate to="/painel" replace />} />
          </Route>
        </Routes>
      </ProvedorJogo>
    </ProvedorConta>
  );
}
