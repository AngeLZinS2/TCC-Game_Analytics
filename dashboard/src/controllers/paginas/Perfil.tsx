/**
 * Perfil: o espaco pessoal da conta dentro do PlayDB.
 *
 * Mesma linguagem visual de Ofertas e Catalogo - o cabecalho usa o
 * `BannerDestaque` das outras duas telas, so que a arte de fundo vem dos
 * jogos QUE A PESSOA favoritou (e, sem favoritos, do mais jogado da Steam
 * agora). O resto sao os mesmos `Painel`/`KpiHud` do resto do dashboard.
 *
 * **O que a referencia de desenho pedia e o backend nao tem** - e por isso
 * nao esta aqui, em vez de virar enfeite sem dado atras:
 *
 * * "Editar perfil": nao existe endpoint de edicao de conta. Um botao que
 *   nao faz nada e pior que a ausencia dele.
 * * Trocar avatar: a foto vem do provedor de login (Google/GitHub) via
 *   `photoURL`; nao ha upload nem storage de avatar no projeto.
 * * "@username": nao existe campo de username. O `@` mostrado e a parte
 *   local do e-mail - o mesmo identificador, nao um campo inventado.
 * * Genero/jogadores/variacao no cartao de jogo favorito: `JogoFavorito`
 *   traz preco, desconto e noticia; contagem de jogadores nao. Os cartoes
 *   mostram o que existe.
 * * Sparkline em todo KPI: so o numero de jogos monitorados tem serie
 *   historica casada (`serie-total`). Os demais mostram o numero seco em
 *   vez de uma curva que nao corresponde aquele indicador.
 *
 * Exige conta - a tela so renderiza dentro de `RotaProtegida` (`App.tsx`).
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import {
  useDesfavoritarEquipe,
  useDesfavoritarJogo,
  useFavoritosEquipes,
  useFavoritosJogos,
  useMaisJogadosSteam,
  usePerfilUsuario,
  useSerieTotalSteam,
  useVisaoGeral,
} from "@models/api/consultas";
import type { EquipeFavorita, JogoFavorito } from "@models/api/tipos";
import { sairDaConta } from "@models/conta/acoes";
import { useUsuario } from "@models/conta/contexto";
import { Botao, Icone, MensagemErro, Selo } from "@views/componentes/base";
import { BannerDestaque } from "@views/componentes/BannerDestaque";
import { BotaoFavoritar } from "@views/componentes/BotaoFavoritar";
import { KpiHud, Painel, Sparkline } from "@views/componentes/hud";
import { CapaJogo } from "@views/componentes/CapaJogo";
import { CapaXbox } from "@views/componentes/CapaXbox";
import { MarcaGithub, MarcaGoogle } from "@views/componentes/MarcasOAuth";
import { corDoJogo } from "@views/tema";
import { fmtData, fmtMoeda, fmtNumero, fmtRelativo } from "@util/formatos";
import { agruparPorDia, useHistoricoAssistente } from "./assistente/historico";
import { PainelChaveIA } from "./conta/PainelChaveIA";

const CDN_STEAM = "https://cdn.cloudflare.steamstatic.com/steam/apps";

function hora(iso: string, idioma: string): string {
  return new Date(iso).toLocaleTimeString(idioma, { hour: "2-digit", minute: "2-digit" });
}

/** Faixas de nivel a partir de perguntas feitas - o unico numero que a conta
 * realmente acumula hoje. Sem pontuacao escondida, so o total em faixas. */
function nivelDoUsuario(totalPerguntas: number, t: TFunction): { rotulo: string; icone: string } {
  if (totalPerguntas >= 20) return { rotulo: t("perfil.nivel.analista"), icone: "workspace_premium" };
  if (totalPerguntas >= 5) return { rotulo: t("perfil.nivel.investigador"), icone: "travel_explore" };
  if (totalPerguntas >= 1) return { rotulo: t("perfil.nivel.curioso"), icone: "psychology" };
  return { rotulo: t("perfil.nivel.novo"), icone: "waving_hand" };
}

function diasComoMembro(iso: string): number {
  const inicio = new Date(iso).getTime();
  return Math.max(0, Math.floor((Date.now() - inicio) / 86_400_000));
}

/** Metodo de login em uso, pelo `providerData` do Firebase - a mesma conta
 * pode ter mais de um vinculado, mas o primeiro e o que autenticou agora. */
function useProvedorLogin(t: TFunction) {
  const { usuario } = useUsuario();
  const providerId = usuario?.providerData[0]?.providerId;

  if (providerId === "google.com") {
    return { rotulo: "Google", icone: <MarcaGoogle /> };
  }
  if (providerId === "github.com") {
    return { rotulo: "GitHub", icone: <MarcaGithub /> };
  }
  return {
    rotulo: t("perfil.provedorEmailSenha"),
    icone: <Icone nome="mail" className="text-[15px] text-primary" />,
  };
}

const CHAVES_ATALHOS = [
  { rota: "/catalogo", chave: "catalogo", icone: "sports_esports" },
  { rota: "/esports", chave: "esports", icone: "emoji_events" },
  { rota: "/recomendacoes", chave: "recomendacoes", icone: "sentiment_satisfied" },
] as const;

export function PerfilPagina() {
  const { t, i18n } = useTranslation();
  const { usuario } = useUsuario();
  const perfil = usePerfilUsuario();
  const historico = useHistoricoAssistente();
  const visaoGeral = useVisaoGeral();
  const maisJogado = useMaisJogadosSteam(1);
  const provedor = useProvedorLogin(t);
  const favoritosJogos = useFavoritosJogos();
  const favoritosEquipes = useFavoritosEquipes();
  const desfavoritarJogo = useDesfavoritarJogo();
  const desfavoritarEquipe = useDesfavoritarEquipe();
  // Mesma consulta que o Catalogo ja faz (cache do TanStack Query compartilha
  // a resposta): serve so para o sparkline do KPI de jogos monitorados.
  const serieCatalogo = useSerieTotalSteam(7);
  const [saindo, setSaindo] = useState(false);

  async function sair() {
    setSaindo(true);
    try {
      await sairDaConta();
    } finally {
      setSaindo(false);
    }
  }

  const grupos = agruparPorDia(historico.entradas, t, i18n.language);
  const nivel = useMemo(
    () => nivelDoUsuario(perfil.data?.total_perguntas_assistente ?? 0, t),
    [perfil.data?.total_perguntas_assistente, t],
  );
  const dias = perfil.data ? diasComoMembro(perfil.data.membro_desde) : null;
  const primeiroJogo = maisJogado.data?.[0];
  const apelido = (usuario?.email ?? perfil.data?.email ?? "").split("@")[0];
  const nome = perfil.data?.nome_exibicao || usuario?.displayName || apelido;

  // A arte do cabecalho sao OS JOGOS DA PESSOA. Sem favoritos, cai no mais
  // jogado da Steam agora - nunca uma ilustracao generica.
  const imagensHero = useMemo(() => {
    const dosFavoritos = (favoritosJogos.data ?? [])
      .map((j) => j.imagem ?? (j.fonte === "steam" ? `${CDN_STEAM}/${j.jogo_id}/header.jpg` : null))
      .filter((url): url is string => Boolean(url));
    if (dosFavoritos.length > 0) return dosFavoritos.slice(0, 8);
    return primeiroJogo ? [`${CDN_STEAM}/${primeiroJogo.app_id}/header.jpg`] : [];
  }, [favoritosJogos.data, primeiroJogo]);

  const serieJogos = (serieCatalogo.data ?? []).map((p) => p.jogos ?? 0);

  return (
    <>
      {/* ==================== CABEÇALHO ==================== */}
      <BannerDestaque imagens={imagensHero}>
        <div className="flex flex-wrap items-center justify-between gap-space-lg">
          <div className="flex items-center gap-space-base">
            {usuario?.photoURL ? (
              <img
                src={usuario.photoURL}
                alt=""
                className="h-20 w-20 shrink-0 rounded-full object-cover ring-2 ring-primary-container/40"
              />
            ) : (
              <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-primary-container/20 font-headline-lg text-headline-lg font-bold text-primary ring-2 ring-primary-container/40">
                {(nome || "?").charAt(0).toUpperCase()}
              </div>
            )}

            <div className="flex min-w-0 flex-col gap-space-xxs">
              <h1 className="font-headline-lg text-headline-lg font-bold text-on-surface">
                {t("perfil.ola", { nome })}
              </h1>
              {apelido && (
                <span className="font-title-code text-title-code text-primary">@{apelido}</span>
              )}

              <div className="flex flex-wrap items-center gap-space-xs pt-space-xxs">
                {perfil.data && (
                  <Selo cor="neutro">
                    <Icone nome="calendar_today" className="text-[12px]" />
                    {t("perfil.membroDesdeData", { data: fmtData(perfil.data.membro_desde) })}
                  </Selo>
                )}
                <Selo cor="primario">
                  <Icone nome={nivel.icone} className="text-[13px]" />
                  {nivel.rotulo}
                </Selo>
                <Selo cor="neutro">
                  {provedor.icone}
                  {provedor.rotulo}
                </Selo>
                {/* `emailVerified` é do Firebase e é real - diferente de um
                    "conta ativa" decorativo, que seria sempre verdadeiro
                    (só quem está logado vê esta tela). */}
                {usuario?.emailVerified && (
                  <Selo cor="positivo">
                    <Icone nome="verified" className="text-[12px]" />
                    {t("perfil.emailVerificado")}
                  </Selo>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-space-xs pt-space-sm">
                <Botao icone="logout" aoClicar={sair} desabilitado={saindo}>
                  {t("perfil.sair")}
                </Botao>
              </div>
            </div>
          </div>

          {/* Fundo próprio: este canto cai sobre a arte do jogo, onde o
              gradiente do banner já clareou - sem a chapa, o número some em
              capas claras. */}
          {dias !== null && (
            <div className="hidden flex-col items-end rounded-xl bg-surface-container-lowest/85 px-space-base py-space-sm text-right ring-1 ring-outline-variant/25 backdrop-blur-sm lg:flex">
              <span className="font-headline-lg text-headline-lg font-bold tabular-nums text-on-surface">
                {fmtNumero(dias)}
              </span>
              <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                {t(dias === 1 ? "perfil.diaNoPlaydb" : "perfil.diasNoPlaydb")}
              </span>
            </div>
          )}
        </div>
      </BannerDestaque>

      {/* ============ CONTA · IA · PULSO DO PLAYDB ============ */}
      <div className="grid gap-space-base xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.1fr)_minmax(0,1.6fr)]">
        <Painel icone="badge" titulo={t("perfil.suaConta.titulo")}>
          {perfil.isError ? (
            <MensagemErro erro={perfil.error} />
          ) : (
            <div className="flex flex-col gap-space-sm">
              <CampoConta
                rotulo={t("perfil.suaConta.email")}
                valor={usuario?.email ?? perfil.data?.email ?? "—"}
                carregando={perfil.isPending}
              />
              <CampoConta
                rotulo={t("perfil.suaConta.identificador")}
                valor={apelido ? `@${apelido}` : "—"}
                carregando={perfil.isPending}
              />
              <CampoConta
                rotulo={t("perfil.suaConta.membroDesde")}
                valor={perfil.data ? fmtData(perfil.data.membro_desde) : "—"}
                carregando={perfil.isPending}
              />
            </div>
          )}
        </Painel>

        {/* O painel da chave de IA já trata mascaramento, troca e remoção -
            reusado inteiro, sem tocar na parte de segurança. */}
        <PainelChaveIA perfil={perfil.data} />

        <Painel
          icone="bolt"
          titulo={t("perfil.playdbAgora.titulo")}
          descricao={t("perfil.playdbAgora.descricao")}
          meta={
            <Selo cor="positivo">
              <Icone nome="sensors" className="text-[12px]" />
              {t("perfil.playdbAgora.emTempoReal")}
            </Selo>
          }
        >
          {visaoGeral.isError ? (
            <MensagemErro erro={visaoGeral.error} />
          ) : (
            <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2">
              <KpiHud
                etiqueta={t("perfil.playdbAgora.catalogo")}
                // MONITORADOS (com ficha) + Xbox. `jogos_steam` conta a
                // dimensão inteira, que desde a varredura de ofertas inclui
                // ~18 mil apps sem ficha - o rótulo aqui diz "monitorados".
                valor={visaoGeral.data ? fmtNumero(visaoGeral.data.jogos_steam_monitorados + visaoGeral.data.jogos_xbox) : "—"}
                valorNumerico={visaoGeral.data ? visaoGeral.data.jogos_steam_monitorados + visaoGeral.data.jogos_xbox : null}
                formatarValor={fmtNumero}
                rotulo={t("perfil.playdbAgora.jogosMonitorados")}
                acento="primaria"
              >
                {/* Única série que casa com o indicador ao lado. */}
                <Sparkline valores={serieJogos} />
              </KpiHud>

              <KpiHud
                etiqueta={t("perfil.playdbAgora.valve")}
                valor={visaoGeral.data?.steam_usuarios_online != null ? fmtNumero(visaoGeral.data.steam_usuarios_online) : "—"}
                valorNumerico={visaoGeral.data?.steam_usuarios_online ?? null}
                formatarValor={fmtNumero}
                rotulo={t("perfil.playdbAgora.conectadosSteamAgora")}
                variacao={visaoGeral.data?.steam_usuarios_online_variacao ?? null}
                notaVariacao={t("perfil.playdbAgora.vsColetaAnterior")}
                acento="secundaria"
              />

              <KpiHud
                etiqueta={t("perfil.playdbAgora.starSchema")}
                valor={visaoGeral.data ? fmtNumero(visaoGeral.data.partidas) : "—"}
                valorNumerico={visaoGeral.data?.partidas ?? null}
                formatarValor={fmtNumero}
                rotulo={t("perfil.playdbAgora.partidasColetadas")}
                acento="terciaria"
              />

              <KpiHud
                etiqueta={t("perfil.playdbAgora.dimensao")}
                valor={visaoGeral.data ? fmtNumero(visaoGeral.data.jogadores) : "—"}
                valorNumerico={visaoGeral.data?.jogadores ?? null}
                formatarValor={fmtNumero}
                rotulo={t("perfil.playdbAgora.jogadoresIdentificados")}
                acento="primaria"
              />
            </div>
          )}
        </Painel>
      </div>

      {/* ============ MAIS JOGADO · ATIVIDADE COM IA ============ */}
      <div className="grid gap-space-base xl:grid-cols-2">
        <Painel icone="sports_esports" titulo={t("perfil.playdbAgora.maisJogadoAgora")}>
          {maisJogado.isPending ? (
            <div className="h-24 animate-pulse rounded-lg bg-surface-container-high/60" aria-hidden />
          ) : !primeiroJogo ? (
            <p className="font-body-sm text-body-sm text-outline">
              {t("perfil.playdbAgora.semMaisJogado")}
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-space-base">
              <img
                src={`${CDN_STEAM}/${primeiroJogo.app_id}/header.jpg`}
                alt=""
                className="h-24 w-44 shrink-0 rounded-lg object-cover shadow-lg"
              />
              <div className="flex min-w-0 flex-1 flex-col gap-space-xxs">
                <span className="truncate font-headline-sm text-headline-sm font-bold text-on-surface">
                  {primeiroJogo.nome ?? `App ${primeiroJogo.app_id}`}
                </span>
                <span className="flex items-center gap-space-xs">
                  <span className="flex items-center gap-space-xxs font-headline-sm text-headline-sm font-bold tabular-nums text-primary">
                    <Icone nome="group" className="text-[16px] text-outline" />
                    {fmtNumero(primeiroJogo.jogadores_agora)}
                  </span>
                  {primeiroJogo.variacao_semana !== null && (
                    <Selo cor={primeiroJogo.variacao_semana >= 0 ? "positivo" : "negativo"}>
                      <Icone
                        nome={primeiroJogo.variacao_semana >= 0 ? "arrow_upward" : "arrow_downward"}
                        className="text-[12px]"
                      />
                      {Math.abs(primeiroJogo.variacao_semana).toFixed(1)}%
                    </Selo>
                  )}
                </span>
                <span className="font-label-caps text-label-caps text-outline">
                  {t("perfil.playdbAgora.jogando")}
                </span>
              </div>
              <Link
                to={`/steam/${primeiroJogo.app_id}`}
                className="shrink-0 rounded-full bg-primary-container px-space-md py-space-xs font-title-code text-title-code font-bold text-on-primary transition-colors hover:brightness-110"
              >
                {t("perfil.playdbAgora.verJogo")} →
              </Link>
            </div>
          )}
        </Painel>

        <Painel
          icone="smart_toy"
          titulo={t("perfil.perguntasAssistente.titulo")}
          descricao={t("perfil.perguntasAssistente.descricao")}
          meta={
            <Link
              to="/assistente"
              className="flex items-center gap-space-xxs font-title-code text-title-code text-primary hover:underline"
            >
              {t("perfil.perguntasAssistente.abrirAssistente")}
              <Icone nome="arrow_forward" className="text-[14px]" />
            </Link>
          }
        >
          {historico.carregando ? (
            <div className="flex flex-col gap-space-xs" aria-hidden>
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-10 animate-pulse rounded bg-surface-container-high/60" />
              ))}
            </div>
          ) : grupos.length === 0 ? (
            <VazioComAcao
              icone="forum"
              texto={t("perfil.perguntasAssistente.vazioPrefixo")}
              rota="/assistente"
              acao={t("perfil.perguntasAssistente.vazioLink")}
            />
          ) : (
            <div className="flex flex-col gap-space-sm">
              {grupos.map((grupo) => (
                <div key={grupo.dia}>
                  <div className="pb-space-xxs font-badge-status text-badge-status uppercase tracking-wider text-outline/70">
                    {grupo.dia}
                  </div>
                  <ul className="flex flex-col gap-space-xxs">
                    {grupo.itens.map((entrada) => (
                      <li
                        key={entrada.id}
                        className="flex items-center gap-space-sm rounded-lg bg-surface-container-lowest px-space-sm py-space-xs transition-colors hover:bg-surface-container"
                      >
                        <Icone
                          nome={
                            entrada.util === true
                              ? "thumb_up"
                              : entrada.util === false
                                ? "thumb_down"
                                : "chat_bubble"
                          }
                          className="shrink-0 text-[14px] text-primary"
                        />
                        <span className="min-w-0 flex-1 truncate font-body-sm text-body-sm text-on-surface-variant">
                          {entrada.pergunta}
                        </span>
                        <span className="shrink-0 font-badge-status text-badge-status tabular-nums text-outline">
                          {hora(entrada.em, i18n.language)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}

              <button
                type="button"
                onClick={historico.limpar}
                className="mt-space-xs flex items-center justify-center gap-space-xs self-start rounded border border-outline-variant/30 px-space-base py-space-xs font-title-code text-title-code text-outline transition-colors hover:border-error/40 hover:text-error focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
              >
                <Icone nome="delete" className="text-[16px]" />
                {t("perfil.perguntasAssistente.limpar")}
              </button>
            </div>
          )}
        </Painel>
      </div>

      {/* ============ FAVORITOS · EXPLORE ============ */}
      <div className="grid gap-space-base xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <Painel
          icone="favorite"
          titulo={t("perfil.jogosFavoritos.titulo")}
          descricao={t("perfil.jogosFavoritos.descricao")}
        >
          {favoritosJogos.isError ? (
            <MensagemErro erro={favoritosJogos.error} />
          ) : favoritosJogos.isPending ? (
            <div className="grid grid-cols-2 gap-space-sm" aria-hidden>
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-40 animate-pulse rounded-lg bg-surface-container-high/60" />
              ))}
            </div>
          ) : (favoritosJogos.data ?? []).length === 0 ? (
            <VazioComAcao
              icone="favorite_border"
              texto={t("perfil.jogosFavoritos.vazioPrefixo")}
              rota="/catalogo/steam"
              acao={t("perfil.jogosFavoritos.vazioLink")}
            />
          ) : (
            <div className="grid grid-cols-1 gap-space-sm sm:grid-cols-2">
              {favoritosJogos.data.map((jogo) => (
                <CartaoJogoFavorito
                  key={`${jogo.fonte}-${jogo.jogo_id}`}
                  jogo={jogo}
                  ocupado={desfavoritarJogo.isPending}
                  aoRemover={() =>
                    desfavoritarJogo.mutate({ fonte: jogo.fonte, jogo_id: jogo.jogo_id })
                  }
                />
              ))}
            </div>
          )}
        </Painel>

        <Painel
          icone="shield"
          titulo={t("perfil.timesFavoritos.titulo")}
          descricao={t("perfil.timesFavoritos.descricao")}
        >
          {favoritosEquipes.isError ? (
            <MensagemErro erro={favoritosEquipes.error} />
          ) : favoritosEquipes.isPending ? (
            <div className="flex flex-col gap-space-xs" aria-hidden>
              {[0, 1].map((i) => (
                <div key={i} className="h-16 animate-pulse rounded-lg bg-surface-container-high/60" />
              ))}
            </div>
          ) : (favoritosEquipes.data ?? []).length === 0 ? (
            <VazioComAcao
              icone="shield"
              texto={t("perfil.timesFavoritos.vazioPrefixo")}
              rota="/esports"
              acao={t("perfil.timesFavoritos.vazioLink")}
            />
          ) : (
            <div className="flex flex-col gap-space-xs">
              {favoritosEquipes.data.map((equipe) => (
                <LinhaEquipeFavorita
                  key={equipe.id_equipe}
                  equipe={equipe}
                  ocupado={desfavoritarEquipe.isPending}
                  aoRemover={() => desfavoritarEquipe.mutate(equipe.id_equipe)}
                />
              ))}
            </div>
          )}
        </Painel>

        <Painel
          icone="explore"
          titulo={t("perfil.exploreMais.titulo")}
          descricao={t("perfil.exploreMais.descricao")}
        >
          <div className="flex flex-col gap-space-xs">
            {CHAVES_ATALHOS.map((atalho) => (
              <Link
                key={atalho.rota}
                to={atalho.rota}
                className="group flex items-start gap-space-sm rounded-lg bg-surface-container-lowest p-space-base transition-all duration-200 hover:bg-surface-container-high hover:ring-1 hover:ring-primary/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
              >
                <span className="mt-[2px] flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-container/15 text-primary">
                  <Icone nome={atalho.icone} className="text-[18px]" />
                </span>
                <div className="min-w-0 flex-1">
                  <span className="font-title-code text-title-code font-bold text-on-surface">
                    {t(`perfil.exploreMais.${atalho.chave}.rotulo`)}
                  </span>
                  <p className="font-body-sm text-body-sm text-outline">
                    {t(`perfil.exploreMais.${atalho.chave}.descricao`)}
                  </p>
                </div>
                <Icone
                  nome="arrow_forward"
                  className="mt-[2px] shrink-0 text-[16px] text-outline transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
                />
              </Link>
            ))}
          </div>
        </Painel>
      </div>
    </>
  );
}

function CampoConta({
  rotulo,
  valor,
  carregando,
}: {
  rotulo: string;
  valor: string;
  carregando: boolean;
}) {
  return (
    <div className="flex flex-col gap-space-xxs rounded-lg bg-surface-container-lowest p-space-base">
      <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
        {rotulo}
      </span>
      {carregando ? (
        <div className="h-5 w-32 animate-pulse rounded bg-surface-container-high/60" aria-hidden />
      ) : (
        <span className="truncate font-body-md text-body-md text-on-surface">{valor}</span>
      )}
    </div>
  );
}

/** Vazio com uma saída - um estado vazio sem para onde ir é um beco. */
function VazioComAcao({
  icone,
  texto,
  rota,
  acao,
}: {
  icone: string;
  texto: string;
  rota: string;
  acao: string;
}) {
  return (
    <div className="flex flex-col items-center gap-space-sm rounded-lg bg-surface-container-lowest/60 px-space-base py-space-lg text-center">
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-container/10 text-primary">
        <Icone nome={icone} className="text-[20px]" />
      </span>
      <p className="font-body-sm text-body-sm text-on-surface-variant">{texto}</p>
      <Link
        to={rota}
        className="flex items-center gap-space-xxs font-title-code text-title-code text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      >
        {acao}
        <Icone nome="arrow_forward" className="text-[14px]" />
      </Link>
    </div>
  );
}

/**
 * Cartão de um jogo favorito.
 *
 * Mostra preço, desconto e a última notícia porque é o que `JogoFavorito`
 * carrega - contagem de jogadores e gênero não vêm neste endpoint, e buscá-los
 * seria uma requisição por cartão.
 */
function CartaoJogoFavorito({
  jogo,
  ocupado,
  aoRemover,
}: {
  jogo: JogoFavorito;
  ocupado: boolean;
  aoRemover: () => void;
}) {
  const { t } = useTranslation();
  const destino = jogo.fonte === "steam" ? `/steam/${jogo.jogo_id}` : `/xbox/${jogo.jogo_id}`;

  return (
    <article className="group flex flex-col overflow-hidden rounded-lg border border-outline-variant/15 bg-surface-container-lowest transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5">
      <div className="relative">
        <Link to={destino} className="block">
          {jogo.fonte === "steam" ? (
            <CapaJogo
              appId={Number(jogo.jogo_id)}
              nome={jogo.nome}
              imagemUrl={jogo.imagem}
              className="h-24 w-full rounded-none object-cover transition-transform duration-200 group-hover:scale-105"
            />
          ) : (
            <CapaXbox
              nome={jogo.nome}
              imagemUrl={jogo.imagem}
              className="h-24 w-full rounded-none object-cover transition-transform duration-200 group-hover:scale-105"
            />
          )}
        </Link>
        <div className="absolute right-space-xs top-space-xs">
          <BotaoFavoritar favoritado ocupado={ocupado} tamanho="sm" aoAlternar={aoRemover} />
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-space-xxs p-space-sm">
        <Link
          to={destino}
          className="truncate font-title-code text-title-code font-bold text-on-surface hover:text-primary"
        >
          {jogo.nome}
        </Link>

        <div className="mt-auto flex flex-wrap items-center gap-space-xs pt-space-xxs">
          <span className="font-headline-sm text-headline-sm font-bold text-tertiary">
            {jogo.gratuito ? t("jogoSteam.gratuito") : fmtMoeda(jogo.preco_atual, jogo.moeda)}
          </span>
          {jogo.promocao_ativa && jogo.desconto_percentual !== null && (
            <Selo cor="positivo">-{jogo.desconto_percentual}%</Selo>
          )}
        </div>

        {jogo.ultima_noticia_titulo && (
          <a
            href={jogo.ultima_noticia_url ?? undefined}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-start gap-space-xxs font-body-sm text-body-sm text-outline hover:text-primary"
          >
            <Icone nome="campaign" className="mt-[2px] shrink-0 text-[13px]" />
            <span className="truncate">{jogo.ultima_noticia_titulo}</span>
          </a>
        )}
      </div>
    </article>
  );
}

function LinhaEquipeFavorita({
  equipe,
  ocupado,
  aoRemover,
}: {
  equipe: EquipeFavorita;
  ocupado: boolean;
  aoRemover: () => void;
}) {
  const { t } = useTranslation();

  return (
    <article className="flex items-center gap-space-sm rounded-lg bg-surface-container-lowest p-space-sm transition-colors hover:bg-surface-container">
      {equipe.logo_url ? (
        <img src={equipe.logo_url} alt="" className="h-11 w-11 shrink-0 rounded object-contain" />
      ) : (
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded bg-surface-container-high font-headline-sm text-headline-sm text-outline">
          {equipe.nome.charAt(0).toUpperCase()}
        </div>
      )}

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-space-xs">
          <span className="truncate font-title-code text-title-code font-bold text-on-surface">
            {equipe.nome}
          </span>
          <span
            className="shrink-0 rounded bg-surface-container-highest px-space-xs py-[1px] font-badge-status text-badge-status uppercase"
            style={{ color: corDoJogo(equipe.jogo_codigo) }}
          >
            {equipe.jogo_codigo}
          </span>
        </div>

        {equipe.proxima_partida ? (
          <p className="font-body-sm text-body-sm text-on-surface-variant">
            vs. <strong className="text-on-surface">{equipe.proxima_partida.adversario_nome}</strong>{" "}
            <span className="text-outline">
              · {fmtRelativo(equipe.proxima_partida.inicio_previsto)}
            </span>
          </p>
        ) : (
          <p className="font-body-sm text-body-sm text-outline">
            {t("perfil.timesFavoritos.semPartidaAgendada")}
          </p>
        )}
      </div>

      <BotaoFavoritar favoritado ocupado={ocupado} tamanho="sm" aoAlternar={aoRemover} />
    </article>
  );
}
