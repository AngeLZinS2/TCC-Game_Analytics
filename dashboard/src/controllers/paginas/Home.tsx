/**
 * A Home: a landing cinematográfica que qualquer pessoa vê antes de entrar
 * no painel - a porta de entrada do TCC, não o instrumento em si.
 *
 * Fora do `LayoutDashboard` de propósito (ver o comentário dele): aqui não
 * tem trilho lateral, barra superior nem nav inferior - é tela cheia, um
 * scroll só, e um botão no fim de cada trecho te leva pro painel de verdade.
 *
 * O "3D" é Canvas 2D + CSS, não WebGL (decisão registrada com o usuário): uma
 * rede de pontos à deriva no herói (`FundoParticulas`), paralaxe de mouse nas
 * camadas (`useParalaxeMouse`), tilt em `perspective()` nos cartões e uma
 * parede de capas boiando com leve rotação por tile. Zero dependência nova.
 *
 * Nada aqui é maquete: os números do herói e as capas da parede vêm da API de
 * verdade (`useVisaoGeral`, `useMaisJogadosSteam`), com o mesmo princípio do
 * resto do projeto - se o dado não carregou, o número não aparece inventado.
 */

import { useMemo, useState, type MouseEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useDestaquesHome, useMaisJogadosSteam, useVisaoGeral } from "@models/api/consultas";
import { useContagem, useVisivel } from "@models/hooks/animacao";
import { useParalaxeMouse } from "@models/hooks/paralaxe";
import { Icone } from "@views/componentes/base";
import { CapaJogo } from "@views/componentes/CapaJogo";
import { FundoParticulas } from "@views/componentes/FundoParticulas";
import { corDoJogo } from "@views/tema";
import { fmtNumero, fmtQuando } from "@util/formatos";

/** Perspectiva do tilt de cartão - baixo o bastante pra não distorcer o texto. */
function aoTiltarCartao(evento: MouseEvent<HTMLElement>) {
  const alvo = evento.currentTarget;
  const retangulo = alvo.getBoundingClientRect();
  const px = (evento.clientX - retangulo.left) / retangulo.width - 0.5;
  const py = (evento.clientY - retangulo.top) / retangulo.height - 0.5;
  alvo.style.transform =
    `perspective(900px) rotateX(${(-py * 9).toFixed(2)}deg) ` +
    `rotateY(${(px * 9).toFixed(2)}deg) translateZ(0)`;
}
function aoDestiltarCartao(evento: MouseEvent<HTMLElement>) {
  evento.currentTarget.style.transform = "";
}

interface Pilar {
  icone: string;
  chave: "catalogo" | "esports" | "modelos" | "assistente";
  destino: string;
  cor: "primary" | "secondary" | "tertiary";
}

const PILARES: Pilar[] = [
  { icone: "sports_esports", chave: "catalogo", destino: "/catalogo/steam", cor: "primary" },
  { icone: "emoji_events", chave: "esports", destino: "/esports", cor: "tertiary" },
  { icone: "model_training", chave: "modelos", destino: "/recomendacoes", cor: "secondary" },
  { icone: "smart_toy", chave: "assistente", destino: "/assistente", cor: "primary" },
];

const CORES_PILAR: Record<Pilar["cor"], { texto: string; anel: string; glow: string }> = {
  primary: { texto: "text-primary", anel: "group-hover:border-primary-container/60", glow: "bg-primary-container/20" },
  secondary: { texto: "text-secondary", anel: "group-hover:border-secondary-fixed-dim/60", glow: "bg-secondary-fixed-dim/20" },
  tertiary: { texto: "text-tertiary", anel: "group-hover:border-tertiary-container/60", glow: "bg-tertiary-container/20" },
};

/** Ângulo fixo por tile, na parede de capas - photos-espalhadas-na-mesa, não
 * aleatório a cada render (isso faria a parede "pular" a cada re-render). */
const ANGULOS_PAREDE = [-6, 4, -3, 7, -5, 8, -7, 3, -4, 6];

function Estatistica({
  valor,
  rotulo,
  sufixo = "",
}: {
  valor: number | null;
  rotulo: string;
  sufixo?: string;
}) {
  return (
    <div className="flex min-w-0 flex-col items-center gap-space-xs px-space-xs py-space-xs">
      <span className="whitespace-nowrap font-title-code text-[clamp(1.15rem,0.8rem+1.6vw,1.875rem)] font-semibold tabular-nums text-on-surface">
        {valor === null ? "—" : fmtNumero(Math.round(valor))}
        {sufixo}
      </span>
      <span className="text-center font-label-caps text-label-caps uppercase tracking-widest text-on-surface-variant">
        {rotulo}
      </span>
    </div>
  );
}

function Secao({
  eyebrow,
  titulo,
  children,
  className = "",
  id,
}: {
  eyebrow: string;
  titulo: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  const [ref, visivel] = useVisivel<HTMLElement>();
  return (
    <section
      ref={ref}
      id={id}
      className={`mx-auto w-full max-w-6xl px-space-base py-space-3xl transition-all duration-700 sm:px-space-lg ${
        visivel ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0"
      } ${className}`}
    >
      <div className="mb-space-xl flex flex-col items-center gap-space-xs text-center">
        <span className="font-label-caps text-label-caps uppercase tracking-[0.2em] text-primary">
          {eyebrow}
        </span>
        <h2 className="max-w-2xl text-balance font-display-hero text-[clamp(1.5rem,1rem+2.2vw,2.5rem)] font-bold leading-tight text-on-surface">
          {titulo}
        </h2>
      </div>
      {children}
    </section>
  );
}

/** Quantos tiles a parede mostra. */
const TAMANHO_PAREDE = 10;

export function HomePagina() {
  const { t } = useTranslation();
  const heroRef = useParalaxeMouse<HTMLDivElement>();
  const geral = useVisaoGeral();
  // Pool maior que o exibido: alguns app_ids não têm o `capsule_231x87.jpg`
  // no caminho determinístico (a Valve migrou pra CDN com hash em jogos
  // recentes - ver o comentário de `CapaJogo`), e mostrar o fallback de
  // letra na parede-vitrine derrota o propósito dela ("prova real", não
  // maquete). Melhor pedir candidatos demais e descartar quem falhar do que
  // aceitar o quadrado de inicial numa seção que existe pra impressionar.
  const maisJogados = useMaisJogadosSteam(30);
  const destaques = useDestaquesHome();
  const [capasFalhas, setCapasFalhas] = useState<Set<number>>(new Set());

  const jogosSteam = useContagem(geral.data?.jogos_steam);
  const partidas = useContagem(geral.data?.partidas);
  const jogadores = useContagem(geral.data?.jogadores);
  const naSteamAgora = useContagem(geral.data?.steam_usuarios_online);

  const aoVivo = destaques.data?.ao_vivo ?? [];
  const capas = useMemo(
    () => (maisJogados.data ?? []).filter((j) => !capasFalhas.has(j.app_id)).slice(0, TAMANHO_PAREDE),
    [maisJogados.data, capasFalhas],
  );

  return (
    <div className="min-h-screen overflow-x-clip bg-background font-body-md text-body-md text-on-surface antialiased selection:bg-primary-container selection:text-on-primary-container">
      {/* ==================== HERÓI ==================== */}
      <div ref={heroRef} className="relative isolate flex min-h-[92dvh] flex-col overflow-hidden">
        <FundoParticulas className="absolute inset-0 h-full w-full" />

        {/* Vinheta: legibilidade do texto sobre a malha de pontos, mais o
            degradê que costura o fim do herói na cor sólida do resto da página. */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 60% 50% at 50% 15%, rgba(90,140,255,0.14), transparent 60%)",
          }}
        />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-48 bg-gradient-to-b from-transparent to-background" />

        <div className="relative z-10 flex flex-1 flex-col items-center justify-center px-space-base py-space-3xl sm:px-space-lg">
          {/* Camada de fundo do paralaxe: desloca pouco, e no sentido oposto
              do texto - a profundidade "atrás do vidro". */}
          <div
            className="flex w-full max-w-4xl flex-col items-center gap-space-lg text-center"
            style={{
              transform:
                "translate3d(calc(var(--mx, 0) * 14px), calc(var(--my, 0) * 10px), 0)",
            }}
          >
            <img
              src="/logo-completo.png"
              alt="PlayDB"
              className="h-28 w-auto drop-shadow-[0_0_44px_rgba(90,140,255,0.35)] sm:h-36"
            />

            <span className="inline-flex items-center gap-space-xs rounded-full border border-outline-variant/40 bg-surface-container-lowest/80 px-space-md py-space-xs font-title-code text-title-code uppercase tracking-widest text-on-surface-variant backdrop-blur-sm">
              <span className="h-2 w-2 animate-pulse rounded-full bg-tertiary" aria-hidden />
              {t("home.eyebrow")}
            </span>

            <h1 className="text-balance font-display-hero text-[clamp(2.5rem,1.5rem+5vw,4.75rem)] font-bold leading-[1.05] tracking-tight text-on-surface">
              {t("home.titulo1")}{" "}
              <span className="bg-gradient-to-r from-primary via-primary-fixed to-tertiary bg-clip-text text-transparent">
                {t("home.tituloDestaque")}
              </span>
            </h1>

            <p className="max-w-2xl text-balance font-body-lg text-body-lg text-on-surface-variant">
              {t("home.descricao")}
            </p>

            <div className="mt-space-sm flex flex-wrap items-center justify-center gap-space-sm">
              <Link
                to="/painel"
                className="group inline-flex items-center gap-space-xs rounded bg-primary-container px-space-lg py-space-sm font-title-code text-title-code text-on-primary shadow-[0_0_32px_-8px_rgba(90,140,255,0.7)] transition-all hover:brightness-110"
              >
                {t("home.ctaEntrarPainel")}
                <Icone
                  nome="arrow_forward"
                  className="text-[18px] transition-transform group-hover:translate-x-1"
                />
              </Link>
              <Link
                to="/assistente"
                className="inline-flex items-center gap-space-xs rounded border border-outline-variant/50 px-space-lg py-space-sm font-title-code text-title-code text-on-surface-variant transition-colors hover:border-outline hover:text-on-surface"
              >
                <Icone nome="smart_toy" className="text-[18px]" />
                {t("home.ctaFalarAssistente")}
              </Link>
            </div>
          </div>

          {/* Camada de primeiro plano do paralaxe: desloca mais - fica "na
              frente" do texto acima dela. */}
          <div
            className="mt-space-3xl grid w-full max-w-4xl grid-cols-1 divide-y divide-outline-variant/20 rounded-xl border border-outline-variant/20 bg-surface-container-lowest/60 px-space-sm py-space-lg backdrop-blur-sm min-[420px]:grid-cols-2 sm:grid-cols-4 sm:divide-x sm:divide-y-0"
            style={{
              transform:
                "translate3d(calc(var(--mx, 0) * -20px), calc(var(--my, 0) * -14px), 0)",
            }}
          >
            <Estatistica valor={jogosSteam} rotulo={t("home.estatisticas.jogosMonitorados")} />
            <Estatistica valor={partidas} rotulo={t("home.estatisticas.partidasColetadas")} />
            <Estatistica valor={jogadores} rotulo={t("home.estatisticas.jogadoresMapeados")} />
            <Estatistica valor={naSteamAgora} rotulo={t("home.estatisticas.naSteamAgora")} />
          </div>
        </div>

        <a
          href="#cobertura"
          className="dica-rolar relative z-10 mb-space-lg flex flex-col items-center gap-space-xxs self-center rounded-full border border-outline-variant/40 bg-surface-container-lowest/80 px-space-md py-space-xs font-label-caps text-label-caps uppercase tracking-widest text-on-surface-variant backdrop-blur-sm transition-colors hover:border-outline hover:text-on-surface"
          aria-label={t("home.rolarAriaLabel")}
        >
          <span>{t("home.rolarParaVerMais")}</span>
          <Icone nome="expand_more" className="text-[20px] text-primary" />
        </a>
      </div>

      {/* ==================== TICKER AO VIVO ==================== */}
      {aoVivo.length > 0 && (
        <div className="border-y border-outline-variant/25 bg-surface-container-lowest/60 py-space-sm">
          <div
            className="rolagem-discreta overflow-hidden"
            style={{
              maskImage:
                "linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent)",
            }}
          >
            <div className="ticker-fita inline-flex gap-space-xl whitespace-nowrap font-title-code text-title-code text-on-surface-variant">
              {[...aoVivo, ...aoVivo].map((c, i) => (
                <span key={i} className="inline-flex items-center gap-space-xs">
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: corDoJogo(c.jogo) }}
                    aria-hidden
                  />
                  <span className="text-on-surface">{c.equipe_a_nome}</span>
                  <span className="text-outline">vs</span>
                  <span className="text-on-surface">{c.equipe_b_nome}</span>
                  <span className="text-outline">
                    {c.ao_vivo ? `· ${t("home.aoVivoAgora")}` : `· ${fmtQuando(c.inicio_previsto)}`}
                  </span>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ==================== PILARES ==================== */}
      <Secao
        id="cobertura"
        eyebrow={t("home.pilares.eyebrow")}
        titulo={
          <>
            {t("home.pilares.tituloPrefixo")}
            <span className="text-primary">{t("home.pilares.tituloDestaque")}</span>
            {t("home.pilares.tituloSufixo")}
          </>
        }
      >
        <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2">
          {PILARES.map((pilar, i) => {
            const cor = CORES_PILAR[pilar.cor];
            return (
              <Link
                key={pilar.chave}
                to={pilar.destino}
                onMouseMove={aoTiltarCartao}
                onMouseLeave={aoDestiltarCartao}
                className={`group relative overflow-hidden rounded-xl border border-outline-variant/25 bg-surface-container-low p-space-lg transition-[border-color,box-shadow] duration-300 will-change-transform ${cor.anel}`}
                style={{ transitionDelay: `${i * 60}ms` }}
              >
                <span
                  className={`pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full opacity-0 blur-3xl transition-opacity duration-500 group-hover:opacity-100 ${cor.glow}`}
                  aria-hidden
                />
                <div className="relative flex flex-col gap-space-sm">
                  <Icone nome={pilar.icone} className={`text-[28px] ${cor.texto}`} />
                  <h3 className="font-headline-md text-headline-md font-semibold text-on-surface">
                    {t(`home.pilares.${pilar.chave}.titulo`)}
                  </h3>
                  <p className="font-body-md text-body-md text-on-surface-variant">
                    {t(`home.pilares.${pilar.chave}.descricao`)}
                  </p>
                  <span className={`mt-space-xs inline-flex items-center gap-space-xxs font-title-code text-title-code ${cor.texto}`}>
                    {t("home.pilares.explorar")}
                    <Icone
                      nome="arrow_forward"
                      className="text-[16px] transition-transform group-hover:translate-x-1"
                    />
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      </Secao>

      {/* ==================== PAREDE DE CAPAS (PROVA REAL) ==================== */}
      <Secao
        eyebrow={t("home.provaReal.eyebrow")}
        titulo={
          <>
            {t("home.provaReal.tituloPrefixo")}
            <span className="text-tertiary">{t("home.provaReal.tituloDestaque")}</span>
            {t("home.provaReal.tituloSufixo")}
          </>
        }
        className="overflow-visible"
      >
        {capas.length > 0 ? (
          <div
            className="mx-auto grid max-w-4xl grid-cols-2 gap-x-space-lg gap-y-space-xl px-space-base py-space-lg sm:grid-cols-4 md:grid-cols-5"
            style={{ perspective: "1200px" }}
          >
            {capas.map((jogo, i) => {
              const angulo = ANGULOS_PAREDE[i % ANGULOS_PAREDE.length];
              return (
                // Dois níveis de proposito: a ROTAÇÃO fixa fica num wrapper
                // estático (inline `style`), o FLUTUAR fica num filho com a
                // animação CSS. Uma animação de `transform` sempre GANHA do
                // `transform` inline no mesmo elemento - juntar os dois numa
                // div só fazia o `rotate()` desaparecer no primeiro quadro.
                <div
                  key={jogo.app_id}
                  className="group transition-transform duration-300 hover:z-10 hover:!rotate-0 hover:scale-110"
                  style={{ transform: `rotate(${angulo}deg)` }}
                >
                  <div
                    className="capa-flutuante flex flex-col items-center gap-space-xxs"
                    style={{ animationDelay: `${i * 0.35}s` }}
                  >
                    <CapaJogo
                      appId={jogo.app_id}
                      nome={jogo.nome ?? `App ${jogo.app_id}`}
                      className="h-16 w-28 rounded-md shadow-lg shadow-black/40 sm:h-20 sm:w-36"
                      aoFalhar={() =>
                        setCapasFalhas((atual) => new Set(atual).add(jogo.app_id))
                      }
                    />
                    <span className="max-w-[7.5rem] truncate font-title-code text-title-code text-on-surface-variant">
                      {jogo.nome ?? `App ${jogo.app_id}`}
                    </span>
                    <span className="font-title-code text-body-sm tabular-nums text-tertiary">
                      {t("home.provaReal.jogando", { contagem: fmtNumero(jogo.jogadores_agora) })}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-center font-body-md text-body-md text-outline">
            {t("home.provaReal.aguardando")}
          </p>
        )}
      </Secao>

      {/* ==================== CHAMADA FINAL ==================== */}
      <div className="border-t border-outline-variant/25 bg-surface-container-lowest/60">
        <div className="mx-auto flex w-full max-w-4xl flex-col items-center gap-space-base px-space-base py-space-3xl text-center sm:px-space-lg">
          <h2 className="font-display-hero text-[clamp(1.5rem,1rem+2.2vw,2.5rem)] font-bold leading-tight text-on-surface">
            {t("home.chamadaFinal.titulo1")}{" "}
            <span className="text-primary">{t("home.chamadaFinal.tituloDestaque")}</span>
          </h2>
          <p className="max-w-xl font-body-lg text-body-lg text-on-surface-variant">
            {t("home.chamadaFinal.descricao")}
          </p>
          <div className="flex flex-wrap items-center justify-center gap-space-sm">
            <Link
              to="/painel"
              className="group inline-flex items-center gap-space-xs rounded bg-primary-container px-space-lg py-space-sm font-title-code text-title-code text-on-primary transition-all hover:brightness-110"
            >
              {t("home.ctaEntrarPainel")}
              <Icone
                nome="arrow_forward"
                className="text-[18px] transition-transform group-hover:translate-x-1"
              />
            </Link>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-space-xs rounded border border-outline-variant/50 px-space-lg py-space-sm font-title-code text-title-code text-on-surface-variant transition-colors hover:border-outline hover:text-on-surface"
            >
              <Icone nome="menu_book" className="text-[18px]" />
              {t("home.chamadaFinal.documentacao")}
            </a>
          </div>
          <p className="mt-space-lg font-label-caps text-label-caps uppercase tracking-widest text-outline">
            {t("home.chamadaFinal.rodape")}
          </p>
        </div>
      </div>
    </div>
  );
}
