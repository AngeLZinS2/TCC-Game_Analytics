/**
 * Perfil: dados da conta + a atividade pessoal que ela acumula - por
 * enquanto so o historico de perguntas ao Assistente de IA, a unica
 * atividade que o site liga a uma conta ate aqui (Fase 31/32).
 *
 * O "nivel" e o "PlayDB agora" nao inventam dado nenhum: o nivel e so uma
 * leitura de `total_perguntas_assistente` (que ja existe) em faixas, e o
 * pulso do site vem do mesmo `/api/visao-geral` que a Visao Geral usa - nada
 * aqui e exclusivo da conta, so reaproveitado num contexto pessoal (o "olha
 * o que rolou desde a ultima vez" que sites como Steam/OP.GG mostram no
 * perfil).
 *
 * Exige conta - a tela so renderiza dentro de `RotaProtegida` (`App.tsx`).
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  useDesfavoritarEquipe,
  useDesfavoritarJogo,
  useFavoritosEquipes,
  useFavoritosJogos,
  useMaisJogadosSteam,
  usePerfilUsuario,
  useVisaoGeral,
} from "@models/api/consultas";
import { sairDaConta } from "@models/conta/acoes";
import { useUsuario } from "@models/conta/contexto";
import { Botao, Icone, MensagemErro, Selo } from "@views/componentes/base";
import { BotaoFavoritar } from "@views/componentes/BotaoFavoritar";
import { KpiHud, Painel } from "@views/componentes/hud";
import { CapaJogo } from "@views/componentes/CapaJogo";
import { CapaXbox } from "@views/componentes/CapaXbox";
import { MarcaGithub, MarcaGoogle } from "@views/componentes/MarcasOAuth";
import { corDoJogo } from "@views/tema";
import { fmtData, fmtMoeda, fmtNumero, fmtRelativo } from "@util/formatos";
import { agruparPorDia, useHistoricoAssistente } from "./assistente/historico";

function hora(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/** Faixas de nivel a partir de perguntas feitas - o unico numero que a conta
 * realmente acumula hoje. Sem pontuacao escondida, so o total em faixas. */
function nivelDoUsuario(totalPerguntas: number): { rotulo: string; icone: string } {
  if (totalPerguntas >= 20) return { rotulo: "Analista de Dados", icone: "workspace_premium" };
  if (totalPerguntas >= 5) return { rotulo: "Investigador", icone: "travel_explore" };
  if (totalPerguntas >= 1) return { rotulo: "Curioso", icone: "psychology" };
  return { rotulo: "Novo por aqui", icone: "waving_hand" };
}

function diasComoMembro(iso: string): number {
  const inicio = new Date(iso).getTime();
  return Math.max(0, Math.floor((Date.now() - inicio) / 86_400_000));
}

/** Metodo de login em uso, pelo `providerData` do Firebase - a mesma conta
 * pode ter mais de um vinculado, mas o primeiro e o que autenticou agora. */
function useProvedorLogin() {
  const { usuario } = useUsuario();
  const providerId = usuario?.providerData[0]?.providerId;

  if (providerId === "google.com") {
    return { rotulo: "Google", icone: <MarcaGoogle /> };
  }
  if (providerId === "github.com") {
    return { rotulo: "GitHub", icone: <MarcaGithub /> };
  }
  return { rotulo: "E-mail e senha", icone: <Icone nome="mail" className="text-[15px] text-primary" /> };
}

const ATALHOS = [
  {
    rota: "/catalogo",
    rotulo: "Catálogo de Jogos",
    descricao: "Steam, Xbox e preços em ~33 lojas",
    icone: "sports_esports",
  },
  {
    rota: "/esports",
    rotulo: "E-Sports",
    descricao: "Partidas, ranking e previsão de confronto",
    icone: "emoji_events",
  },
  {
    rota: "/recomendacoes",
    rotulo: "Recomendações por Reviews",
    descricao: "O que a comunidade está gostando agora",
    icone: "sentiment_satisfied",
  },
] as const;

export function PerfilPagina() {
  const { usuario } = useUsuario();
  const perfil = usePerfilUsuario();
  const historico = useHistoricoAssistente();
  const visaoGeral = useVisaoGeral();
  const maisJogado = useMaisJogadosSteam(1);
  const provedor = useProvedorLogin();
  const favoritosJogos = useFavoritosJogos();
  const favoritosEquipes = useFavoritosEquipes();
  const desfavoritarJogo = useDesfavoritarJogo();
  const desfavoritarEquipe = useDesfavoritarEquipe();
  const [saindo, setSaindo] = useState(false);

  async function sair() {
    setSaindo(true);
    try {
      await sairDaConta();
    } finally {
      setSaindo(false);
    }
  }

  const grupos = agruparPorDia(historico.entradas);
  const nivel = useMemo(
    () => nivelDoUsuario(perfil.data?.total_perguntas_assistente ?? 0),
    [perfil.data?.total_perguntas_assistente],
  );
  const dias = perfil.data ? diasComoMembro(perfil.data.membro_desde) : null;
  const primeiroJogo = maisJogado.data?.[0];

  return (
    <>
      <header className="flex flex-wrap items-center justify-between gap-space-sm">
        <h1 className="flex items-center gap-space-xs font-headline-lg text-headline-lg uppercase tracking-wide text-on-surface">
          <Icone nome="account_circle" className="text-[24px] text-primary" />
          Perfil
        </h1>
        <Botao icone="logout" aoClicar={sair} desabilitado={saindo}>
          Sair
        </Botao>
      </header>

      {/* ==================== RESUMO ==================== */}
      <div className="flex flex-col gap-space-base overflow-hidden rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-space-base">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-primary-container/20 font-headline-lg text-headline-lg text-primary">
            {(usuario?.email ?? "?").charAt(0).toUpperCase()}
          </div>
          <div className="flex flex-col gap-space-xxs">
            <span className="font-headline-sm text-headline-sm text-on-surface">
              Olá, {usuario?.email?.split("@")[0] ?? "visitante"}
            </span>
            <div className="flex flex-wrap items-center gap-space-xs">
              <Selo cor="primario">
                <Icone nome={nivel.icone} className="text-[13px]" />
                {nivel.rotulo}
              </Selo>
              {dias !== null && (
                <Selo cor="neutro">
                  <Icone nome="calendar_today" className="text-[12px]" />
                  {dias === 0 ? "Membro desde hoje" : `Membro há ${fmtNumero(dias)} dia${dias === 1 ? "" : "s"}`}
                </Selo>
              )}
              <Selo cor="neutro">
                {provedor.icone}
                {provedor.rotulo}
              </Selo>
            </div>
          </div>
        </div>
      </div>

      <Painel icone="badge" titulo="Sua conta">
        {perfil.isError ? (
          <MensagemErro erro={perfil.error} />
        ) : (
          <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2">
            <div className="flex flex-col gap-space-xxs rounded-lg bg-surface-container-lowest p-space-base">
              <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                E-mail
              </span>
              <span className="font-body-md text-body-md text-on-surface">
                {usuario?.email ?? perfil.data?.email ?? "—"}
              </span>
            </div>
            <div className="flex flex-col gap-space-xxs rounded-lg bg-surface-container-lowest p-space-base">
              <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                Membro desde
              </span>
              <span className="font-body-md text-body-md text-on-surface">
                {perfil.data ? fmtData(perfil.data.membro_desde) : "—"}
              </span>
            </div>
          </div>
        )}
      </Painel>

      {/* ==================== O PLAYDB AGORA ==================== */}
      <Painel
        icone="bolt"
        titulo="O PlayDB agora"
        descricao="O que o site coletou até agora — os mesmos números da Visão Geral, num resumo rápido."
      >
        {visaoGeral.isError ? (
          <MensagemErro erro={visaoGeral.error} />
        ) : (
          <div className="grid grid-cols-2 gap-space-base lg:grid-cols-4">
            <KpiHud
              etiqueta="Catálogo"
              valor={visaoGeral.data ? fmtNumero(visaoGeral.data.jogos_steam + visaoGeral.data.jogos_xbox) : "—"}
              valorNumerico={visaoGeral.data ? visaoGeral.data.jogos_steam + visaoGeral.data.jogos_xbox : null}
              formatarValor={fmtNumero}
              rotulo="jogos monitorados"
              acento="primaria"
            />
            <KpiHud
              etiqueta="Star schema"
              valor={visaoGeral.data ? fmtNumero(visaoGeral.data.partidas) : "—"}
              valorNumerico={visaoGeral.data?.partidas ?? null}
              formatarValor={fmtNumero}
              rotulo="partidas coletadas"
              acento="terciaria"
            />
            <KpiHud
              etiqueta="Valve"
              valor={visaoGeral.data?.steam_usuarios_online != null ? fmtNumero(visaoGeral.data.steam_usuarios_online) : "—"}
              valorNumerico={visaoGeral.data?.steam_usuarios_online ?? null}
              formatarValor={fmtNumero}
              rotulo="conectados à Steam agora"
              acento="secundaria"
            />
            <KpiHud
              etiqueta="Dimensão"
              valor={visaoGeral.data ? fmtNumero(visaoGeral.data.jogadores) : "—"}
              valorNumerico={visaoGeral.data?.jogadores ?? null}
              formatarValor={fmtNumero}
              rotulo="jogadores identificados"
              acento="primaria"
            />
          </div>
        )}

        {primeiroJogo && (
          <a
            href={`https://store.steampowered.com/app/${primeiroJogo.app_id}/`}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-space-base flex items-center gap-space-sm rounded-lg bg-surface-container-lowest p-space-sm transition-colors hover:bg-surface-container"
          >
            <CapaJogo appId={primeiroJogo.app_id} nome={primeiroJogo.nome ?? "Jogo"} className="h-12 w-12 shrink-0" />
            <div className="min-w-0 flex-1">
              <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                Mais jogado na Steam agora
              </span>
              <p className="truncate font-body-md text-body-md font-bold text-on-surface">
                {primeiroJogo.nome ?? `App ${primeiroJogo.app_id}`}
              </p>
            </div>
            <span className="shrink-0 font-title-code text-title-code text-primary">
              {fmtNumero(primeiroJogo.jogadores_agora)} jogando
            </span>
          </a>
        )}
      </Painel>

      <Painel
        icone="smart_toy"
        titulo="Perguntas ao Assistente de IA"
        descricao="As perguntas que você já fez — só o texto da pergunta, não a resposta."
        meta={
          perfil.data && (
            <div className="min-w-[10rem]">
              <KpiHud
                etiqueta="Total"
                valor={fmtNumero(perfil.data.total_perguntas_assistente)}
                valorNumerico={perfil.data.total_perguntas_assistente}
                formatarValor={fmtNumero}
                rotulo="perguntas"
                acento="primaria"
              />
            </div>
          )
        }
      >
        {historico.carregando ? (
          <div className="flex flex-col gap-space-xs" aria-hidden>
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-surface-container-high/60" />
            ))}
          </div>
        ) : grupos.length === 0 ? (
          <p className="font-body-sm text-body-sm text-outline">
            Nenhuma pergunta ainda. Vá até o{" "}
            <Link to="/assistente" className="text-primary hover:underline">
              Assistente de IA
            </Link>{" "}
            e pergunte algo sobre os dados do PlayDB.
          </p>
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
                      className="flex items-center gap-space-sm rounded bg-surface-container-lowest px-space-sm py-space-xs"
                    >
                      <Icone
                        nome={
                          entrada.util === true
                            ? "thumb_up"
                            : entrada.util === false
                              ? "thumb_down"
                              : "chat_bubble"
                        }
                        className="shrink-0 text-[14px] text-outline"
                      />
                      <span className="min-w-0 flex-1 truncate font-body-sm text-body-sm text-on-surface-variant">
                        {entrada.pergunta}
                      </span>
                      <span className="shrink-0 font-badge-status text-badge-status tabular-nums text-outline">
                        {hora(entrada.em)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}

            <button
              type="button"
              onClick={historico.limpar}
              className="mt-space-xs flex items-center justify-center gap-space-xs self-start rounded border border-outline-variant/30 px-space-base py-space-xs font-title-code text-title-code text-outline transition-colors hover:border-error/40 hover:text-error"
            >
              <Icone nome="delete" className="text-[16px]" />
              Limpar histórico
            </button>
          </div>
        )}
      </Painel>

      {/* ==================== JOGOS FAVORITOS ==================== */}
      <Painel
        icone="favorite"
        titulo="Jogos favoritos"
        descricao="Preço, promoção ativa e a notícia mais recente — o favorito na ficha do jogo (Steam ou Xbox) entra aqui."
      >
        {favoritosJogos.isError ? (
          <MensagemErro erro={favoritosJogos.error} />
        ) : favoritosJogos.data?.length === 0 || favoritosJogos.data === undefined ? (
          favoritosJogos.isPending ? (
            <div className="flex flex-col gap-space-xs" aria-hidden>
              {[0, 1].map((i) => (
                <div key={i} className="h-16 animate-pulse rounded bg-surface-container-high/60" />
              ))}
            </div>
          ) : (
            <p className="font-body-sm text-body-sm text-outline">
              Nenhum jogo favoritado ainda. Vá até o{" "}
              <Link to="/catalogo/steam" className="text-primary hover:underline">
                Catálogo de Jogos
              </Link>{" "}
              e favorite algum na ficha dele.
            </p>
          )
        ) : (
          <div className="grid grid-cols-1 gap-space-sm sm:grid-cols-2">
            {favoritosJogos.data.map((jogo) => (
              <div
                key={`${jogo.fonte}-${jogo.jogo_id}`}
                className="flex items-start gap-space-sm rounded-lg bg-surface-container-lowest p-space-base"
              >
                {jogo.fonte === "steam" ? (
                  <CapaJogo appId={Number(jogo.jogo_id)} nome={jogo.nome} className="h-14 w-14 shrink-0 rounded" />
                ) : (
                  <CapaXbox nome={jogo.nome} imagemUrl={jogo.imagem} className="h-14 w-14 shrink-0 rounded" />
                )}

                <div className="min-w-0 flex-1">
                  <Link
                    to={jogo.fonte === "steam" ? `/steam/${jogo.jogo_id}` : `/xbox/${jogo.jogo_id}`}
                    className="truncate font-title-code text-title-code text-on-surface hover:text-primary"
                  >
                    {jogo.nome}
                  </Link>

                  <div className="mt-space-xxs flex flex-wrap items-center gap-space-xs">
                    <span className="font-body-sm text-body-sm text-on-surface-variant">
                      {jogo.gratuito ? "Gratuito" : fmtMoeda(jogo.preco_atual, jogo.moeda)}
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
                      className="mt-space-xxs flex items-start gap-space-xxs font-body-sm text-body-sm text-outline hover:text-primary"
                    >
                      <Icone nome="campaign" className="mt-[2px] shrink-0 text-[13px]" />
                      <span className="truncate">{jogo.ultima_noticia_titulo}</span>
                    </a>
                  )}
                </div>

                <BotaoFavoritar
                  favoritado
                  ocupado={desfavoritarJogo.isPending}
                  tamanho="sm"
                  aoAlternar={() => desfavoritarJogo.mutate({ fonte: jogo.fonte, jogo_id: jogo.jogo_id })}
                />
              </div>
            ))}
          </div>
        )}
      </Painel>

      {/* ==================== TIMES FAVORITOS ==================== */}
      <Painel
        icone="shield"
        titulo="Times favoritos"
        descricao="Próxima partida agendada — o favorito no seletor da Previsão de Confronto entra aqui."
      >
        {favoritosEquipes.isError ? (
          <MensagemErro erro={favoritosEquipes.error} />
        ) : favoritosEquipes.data?.length === 0 || favoritosEquipes.data === undefined ? (
          favoritosEquipes.isPending ? (
            <div className="flex flex-col gap-space-xs" aria-hidden>
              {[0, 1].map((i) => (
                <div key={i} className="h-16 animate-pulse rounded bg-surface-container-high/60" />
              ))}
            </div>
          ) : (
            <p className="font-body-sm text-body-sm text-outline">
              Nenhum time favoritado ainda. Vá até a{" "}
              <Link to="/esports" className="text-primary hover:underline">
                Previsão de Confronto
              </Link>{" "}
              e favorite um time selecionado.
            </p>
          )
        ) : (
          <div className="grid grid-cols-1 gap-space-sm sm:grid-cols-2">
            {favoritosEquipes.data.map((equipe) => (
              <div
                key={equipe.id_equipe}
                className="flex items-start gap-space-sm rounded-lg bg-surface-container-lowest p-space-base"
              >
                {equipe.logo_url ? (
                  <img src={equipe.logo_url} alt="" className="h-14 w-14 shrink-0 rounded object-contain" />
                ) : (
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded bg-surface-container-high font-headline-sm text-headline-sm text-outline">
                    {equipe.nome.charAt(0).toUpperCase()}
                  </div>
                )}

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-space-xs">
                    <span className="truncate font-title-code text-title-code text-on-surface">
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
                    <p className="mt-space-xxs font-body-sm text-body-sm text-on-surface-variant">
                      vs. <strong className="text-on-surface">{equipe.proxima_partida.adversario_nome}</strong>
                      <br />
                      <span className="text-outline">
                        {fmtRelativo(equipe.proxima_partida.inicio_previsto)}
                        {equipe.proxima_partida.torneio && ` · ${equipe.proxima_partida.torneio}`}
                      </span>
                    </p>
                  ) : (
                    <p className="mt-space-xxs font-body-sm text-body-sm text-outline">
                      Sem partida agendada no momento.
                    </p>
                  )}
                </div>

                <BotaoFavoritar
                  favoritado
                  ocupado={desfavoritarEquipe.isPending}
                  tamanho="sm"
                  aoAlternar={() => desfavoritarEquipe.mutate(equipe.id_equipe)}
                />
              </div>
            ))}
          </div>
        )}
      </Painel>

      {/* ==================== EXPLORE MAIS ==================== */}
      <Painel icone="explore" titulo="Explore mais" descricao="Outras partes do PlayDB que você talvez ainda não tenha visto.">
        <div className="grid grid-cols-1 gap-space-sm sm:grid-cols-3">
          {ATALHOS.map((atalho) => (
            <Link
              key={atalho.rota}
              to={atalho.rota}
              className="flex items-start gap-space-sm rounded-lg bg-surface-container-lowest p-space-base transition-colors hover:bg-surface-container-high"
            >
              <Icone nome={atalho.icone} className="mt-[2px] shrink-0 text-[20px] text-primary" />
              <div className="min-w-0 flex-1">
                <span className="font-title-code text-title-code text-on-surface">{atalho.rotulo}</span>
                <p className="font-body-sm text-body-sm text-outline">{atalho.descricao}</p>
              </div>
              <Icone nome="arrow_forward" className="mt-[2px] shrink-0 text-[16px] text-outline" />
            </Link>
          ))}
        </div>
      </Painel>
    </>
  );
}
