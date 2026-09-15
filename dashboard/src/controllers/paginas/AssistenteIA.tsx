/**
 * Assistente de dados - o espaco de trabalho.
 *
 * Tres areas: historico (esquerda), consulta e resultado (centro), contexto e
 * base da resposta (direita). O painel de contexto nao e enfeite de layout: o
 * modelo de linguagem e o unico componente do projeto capaz de inventar um
 * numero, e mostrar exatamente o que ele recebeu transforma cada resposta em
 * algo conferivel sem sair da pagina.
 *
 * O modelo NAO consulta o banco. O backend monta o contexto com SQL escrito a
 * mao e manda junto da pergunta - a tela deixa isso explicito, porque um
 * assistente que parece ter acesso ao banco e um assistente em que se confia
 * demais.
 *
 * O que o desenho pedia e nao esta aqui, de proposito:
 *
 * - "92% de confianca": o backend nao devolve score. O painel classifica o
 *   CONTEXTO (blocos, linhas, valores comparaveis) e diz que criterio usou.
 * - "Ver consulta" com SQL: as consultas vivem no Python e nunca sobem na
 *   resposta. O botao exigiria inventar o SQL, entao nao existe - "Ver dados"
 *   abre o contexto real.
 * - Historico com perguntas de exemplo: a lista comeca vazia de verdade -
 *   guardada por conta desde a Fase 31 (`assistente/historico.ts`), mas
 *   nunca com uma pergunta que a pessoa nao fez.
 *
 * Exige conta (Fase 31): a tela so renderiza dentro de `RotaProtegida`
 * (`App.tsx`), entao aqui dentro sempre ha um usuario logado.
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { usePerguntarAssistente, useStatusAssistente, useVisaoGeral } from "@models/api/consultas";
import type { RespostaAssistente } from "@models/api/tipos";
import { Icone, MensagemErro, Selo } from "@views/componentes/base";
import { Painel } from "@views/componentes/hud";
import { Modal } from "@views/componentes/Modal";
import { AcoesResposta } from "./assistente/AcoesResposta";
import { BlocoDeContexto, CartaoJogoAoVivo, CartaoJogoRecomendado } from "./assistente/cartoes";
import { CartaoResultado } from "./assistente/CartaoResultado";
import { ComoChegamos } from "./assistente/ComoChegamos";
import { Compositor, sugestoesDe } from "./assistente/Compositor";
import { GraficoSerie } from "./assistente/GraficoSerie";
import { useHistoricoAssistente } from "./assistente/historico";
import { CartaoConfianca, PainelFontes } from "./assistente/PainelContexto";
import { PainelHistorico } from "./assistente/PainelHistorico";
import { Processando } from "./assistente/Processando";
import { StatusApiAssistente } from "./assistente/StatusApi";
import { ROTULO_PROVEDOR } from "./conta/PainelChaveIA";
import { fmtNumero, fmtRelativo } from "@util/formatos";

export function AssistenteIAPagina() {
  const { t } = useTranslation();
  const [pergunta, setPergunta] = useState("");
  const [gavetaHistorico, setGavetaHistorico] = useState(false);
  const [verDados, setVerDados] = useState(false);

  const status = useStatusAssistente();
  const visaoGeral = useVisaoGeral();
  const assistente = usePerguntarAssistente();
  const historico = useHistoricoAssistente();

  const resposta: RespostaAssistente | undefined = assistente.data;
  // A primeira serie e a do bloco mais relevante para a pergunta - a ordem
  // dos blocos vem do backend, nao de reordenar aqui por tamanho.
  const serie = resposta?.series[0];
  // As recomendações vêm de dois caminhos: o catálogo (SQL nosso) ou a busca
  // por característica na loja. O bloco "descoberta" é o que diz qual foi.
  const daLoja = resposta?.blocos.some((b) => b.chave === "descoberta") ?? false;

  const ultimaColeta = useMemo(
    () =>
      visaoGeral.data?.coletas
        .map((c) => c.ultima_coleta)
        .filter((data): data is string => Boolean(data))
        .sort()
        .at(-1) ?? null,
    [visaoGeral.data],
  );

  /** As sugestoes que ainda nao foram a pergunta atual. */
  const continuar = useMemo(
    () => sugestoesDe(t).filter((s) => s.pergunta !== resposta?.pergunta).slice(0, 5),
    [resposta, t],
  );

  function enviar(texto: string) {
    const limpo = texto.trim();
    if (limpo.length < 3) return;
    setPergunta(limpo);
    setGavetaHistorico(false);
    // O historico entra no ar do lado do backend (Fase 31), junto da
    // resposta - `usePerguntarAssistente` ja invalida o cache no sucesso.
    assistente.mutate(limpo);
  }

  const utilAtual =
    historico.entradas.find((e) => e.pergunta === resposta?.pergunta)?.util ?? null;

  // Sem chave o resto da tela nao tem o que fazer - e um estado esperado, nao
  // um erro: o projeto inteiro funciona sem provedor externo.
  if (status.data && !status.data.configurado) {
    return (
      <Painel icone="key_off" titulo={t("assistente.naoConfigurado.titulo")}>
        <p className="font-body-md text-body-md text-on-surface-variant">
          {t("assistente.naoConfigurado.prefixo")}
          <code className="text-primary">OPENROUTER_API_KEY</code>
          {t("assistente.naoConfigurado.meio")}
          <code className="text-primary">.env</code>
          {t("assistente.naoConfigurado.sufixo")}
        </p>
      </Painel>
    );
  }

  return (
    <>
      {/* ==================== CABECALHO ==================== */}
      <header className="flex flex-wrap items-center justify-between gap-space-sm">
        <div className="flex items-center gap-space-sm">
          <button
            type="button"
            onClick={() => setGavetaHistorico(true)}
            className="flex items-center gap-space-xxs rounded bg-surface-container px-space-sm py-space-xs font-title-code text-title-code text-on-surface-variant transition-colors hover:text-primary lg:hidden"
            aria-label={t("assistente.cabecalho.abrirHistorico")}
          >
            <Icone nome="history" className="text-[16px]" />
            {t("assistente.cabecalho.historico")}
          </button>
          <h1 className="flex items-center gap-space-xs font-headline-sm text-headline-sm uppercase tracking-wide text-primary">
            <span aria-hidden>✦</span> {t("assistente.cabecalho.titulo")}
          </h1>
        </div>

        {status.data && (
          <div className="flex flex-wrap items-center gap-space-xs font-badge-status text-badge-status uppercase tracking-wider">
            <span className="flex items-center gap-space-xxs rounded bg-surface-container px-space-sm py-space-xxs text-tertiary">
              <span
                className="h-1.5 w-1.5 rounded-full bg-tertiary shadow-[0_0_6px_rgba(22,239,122,0.8)]"
                aria-hidden
              />
              {t("assistente.cabecalho.iaOnline")}
            </span>
            <span
              className="rounded bg-surface-container px-space-sm py-space-xxs text-outline"
              title={`${status.data.provedor} · ${status.data.modelo}`}
            >
              {status.data.modelo.split("/").pop()?.replace(":free", "")}
            </span>
            <span className="hidden rounded bg-surface-container px-space-sm py-space-xxs text-outline sm:inline">
              {status.data.provedor}
            </span>
          </div>
        )}
      </header>

      <StatusApiAssistente />

      {/* ==================== TRES AREAS ==================== */}
      <div className="grid grid-cols-1 items-start gap-space-base lg:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[240px_minmax(0,1fr)_290px]">
        <aside className="hidden lg:sticky lg:top-[calc(4rem+1.5rem)] lg:block lg:max-h-[calc(100vh-7rem)]">
          <PainelHistorico
            entradas={historico.entradas}
            carregando={historico.carregando}
            perguntaAtual={resposta?.pergunta ?? null}
            aoEscolher={(texto) => setPergunta(texto)}
            aoLimpar={historico.limpar}
          />
        </aside>

        <main className="flex min-w-0 flex-col gap-space-base">
          <div>
            <h2 className="font-headline-lg text-headline-lg text-on-surface">
              {t("assistente.main.titulo")}
            </h2>
            <p className="font-body-sm text-body-sm text-outline">
              {t("assistente.main.descricao")}
            </p>
          </div>

          <Compositor
            valor={pergunta}
            aoMudar={setPergunta}
            aoEnviar={() => enviar(pergunta)}
            ocupado={assistente.isPending}
            fontesDisponiveis={visaoGeral.data?.coletas.length ?? null}
            atualizadoEm={ultimaColeta ? fmtRelativo(ultimaColeta) : null}
          />

          {assistente.isError && (
            <div className="flex flex-col gap-space-sm rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl">
              <div className="flex items-center gap-space-xs font-headline-sm text-headline-sm text-error">
                <Icone nome="error" className="text-[20px]" />
                {t("assistente.erro.titulo")}
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant">
                {t("assistente.erro.corpo")}
              </p>
              <MensagemErro erro={assistente.error} />
              <button
                type="button"
                onClick={() => enviar(pergunta)}
                className="self-start rounded bg-primary-container px-space-base py-space-xs font-title-code text-title-code text-on-primary transition-all hover:brightness-110"
              >
                {t("assistente.erro.tentarNovamente")}
              </button>
            </div>
          )}

          {assistente.isPending && <Processando />}

          {/* ---------- ESTADO VAZIO ---------- */}
          {!resposta && !assistente.isPending && !assistente.isError && (
            <div className="flex flex-col items-center gap-space-sm rounded-xl bg-surface-container-low/60 px-space-lg py-space-3xl text-center">
              <span className="text-[32px] text-primary drop-shadow-[0_0_16px_rgba(90,140,255,0.5)]" aria-hidden>
                ✦
              </span>
              <h3 className="font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
                {t("assistente.vazio.titulo")}
              </h3>
              <p className="max-w-md font-body-sm text-body-sm text-outline">
                {t("assistente.vazio.corpo")}{" "}
                {visaoGeral.data && (
                  <>
                    {t("assistente.vazio.comDados", {
                      jogos: fmtNumero(visaoGeral.data.jogos_steam),
                      partidas: fmtNumero(visaoGeral.data.partidas),
                    })}
                  </>
                )}
              </p>
            </div>
          )}

          {/* ---------- RESULTADO ---------- */}
          {resposta && !assistente.isPending && (
            <>
              {serie && (
                <div className="grid grid-cols-1 gap-space-base lg:grid-cols-2">
                  <section className="rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl">
                    <CartaoResultado serie={serie} pergunta={resposta.pergunta} />
                  </section>
                  {/* `justify-center`: o cartao ao lado costuma ser mais alto
                      (tem a lista inteira), e o grafico ancorado no topo
                      deixaria um vazio grande embaixo. */}
                  <section className="flex min-w-0 flex-col justify-center rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl">
                    <GraficoSerie serie={serie} />
                  </section>
                </div>
              )}

              <section className="flex flex-col gap-space-base rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl">
                <div className="flex flex-wrap items-center justify-between gap-space-xs">
                  <span className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-primary">
                    <Icone nome="chat" className="text-[16px]" />
                    {t("assistente.resposta.label")}
                  </span>
                  <span className="flex items-center gap-space-xs">
                    {resposta.usando_chave_propria && (
                      <Selo cor="positivo">
                        <Icone nome="vpn_key" className="text-[12px]" />
                        {t("assistente.resposta.suaChave")}
                        {resposta.provedor_ia ? ` · ${ROTULO_PROVEDOR[resposta.provedor_ia]}` : ""}
                      </Selo>
                    )}
                    <span className="font-badge-status text-badge-status uppercase tracking-wider text-outline">
                      {t("assistente.resposta.tokens", {
                        entrada: fmtNumero(resposta.tokens_entrada),
                        saida: fmtNumero(resposta.tokens_saida),
                      })}
                    </span>
                  </span>
                </div>

                <p className="whitespace-pre-line font-body-lg text-body-lg text-on-surface">
                  {resposta.resposta}
                </p>

                <p className="flex items-start gap-space-xs font-body-sm text-body-sm text-outline">
                  <Icone nome="info" className="mt-[2px] text-[16px] text-primary" />
                  {t("assistente.resposta.redigidoPrefixo")}{" "}
                  <span className="text-on-surface">{resposta.modelo}</span>{" "}
                  {t("assistente.resposta.redigidoSufixo")}
                </p>

                {resposta.fontes_web.length > 0 && (
                  <div className="flex flex-col gap-space-xs border-t border-outline-variant/20 pt-space-base">
                    <span className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-outline">
                      <Icone nome="travel_explore" className="text-[15px]" />
                      {t("assistente.resposta.fontesWeb")}
                    </span>
                    {resposta.fontes_web.map((f) => (
                      <a
                        key={f.url}
                        href={f.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-space-xs font-body-sm text-body-sm text-on-surface-variant transition-colors hover:text-primary"
                      >
                        <Icone nome="open_in_new" className="text-[13px] text-outline" />
                        <span className="truncate">{f.titulo}</span>
                      </a>
                    ))}
                  </div>
                )}

                <AcoesResposta
                  resposta={resposta}
                  util={utilAtual}
                  aoAvaliar={(util) => historico.avaliar(resposta.pergunta, util)}
                  aoVerDados={() => setVerDados(true)}
                />
              </section>

              {resposta.jogo_ao_vivo && (
                <Painel
                  icone="storefront"
                  titulo={t("assistente.jogoIdentificado.titulo")}
                  descricao={t("assistente.jogoIdentificado.descricao")}
                >
                  <CartaoJogoAoVivo jogo={resposta.jogo_ao_vivo} />
                </Painel>
              )}

              {resposta.recomendacoes.length > 0 && (
                <Painel
                  icone="stadia_controller"
                  titulo={t("assistente.recomendados.titulo")}
                  descricao={
                    // A mesma lista sai de dois caminhos diferentes, e dizer o
                    // caminho errado é dizer a procedência errada: "a partir do
                    // catálogo" numa lista que veio da loja afirmaria que esses
                    // jogos são coletados por nós, o que não é verdade.
                    daLoja
                      ? t("assistente.recomendados.descricaoLoja")
                      : t("assistente.recomendados.descricaoCatalogo")
                  }
                >
                  <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2 xl:grid-cols-3">
                    {resposta.recomendacoes.map((jogo) => (
                      <CartaoJogoRecomendado key={jogo.app_id} jogo={jogo} />
                    ))}
                  </div>
                </Painel>
              )}

              <ComoChegamos resposta={resposta} />

              {/*
                "Continuar explorando" e nao "perguntas relacionadas": elas sao
                fixas, escolhidas por exercitarem blocos de contexto
                diferentes. Gerar variacoes sobre a resposta exigiria pedir ao
                modelo - outra chamada, e outra chance de inventar entidade.
              */}
              <section className="flex flex-col gap-space-sm rounded-xl bg-surface-container-low/90 p-space-lg shadow-2xl">
                <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  {t("assistente.continuarExplorando")}
                </span>
                <div className="grid grid-cols-1 gap-space-xs sm:grid-cols-2 xl:grid-cols-3">
                  {continuar.map((sugestao) => (
                    <button
                      key={sugestao.rotulo}
                      type="button"
                      onClick={() => enviar(sugestao.pergunta)}
                      className="flex items-center justify-between gap-space-sm rounded-lg bg-surface-container-lowest px-space-base py-space-sm text-left font-body-sm text-body-sm text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface"
                    >
                      {sugestao.pergunta}
                      <Icone nome="arrow_forward" className="shrink-0 text-[16px] text-primary" />
                    </button>
                  ))}
                </div>
              </section>
            </>
          )}

          {/* Contexto vira secao no lugar da lateral quando ela nao cabe. */}
          <div className="flex flex-col gap-space-base xl:hidden">
            <PainelFontes
              resposta={resposta}
              visaoGeral={visaoGeral.data}
              aoVerDados={() => setVerDados(true)}
            />
            {resposta && !assistente.isPending && <CartaoConfianca resposta={resposta} />}
          </div>

          <ComoFunciona />
        </main>

        <aside className="hidden xl:sticky xl:top-[calc(4rem+1.5rem)] xl:flex xl:flex-col xl:gap-space-base">
          <PainelFontes
            resposta={resposta}
            visaoGeral={visaoGeral.data}
            aoVerDados={() => setVerDados(true)}
          />
          {resposta && !assistente.isPending && <CartaoConfianca resposta={resposta} />}

          <div className="rounded-xl bg-surface-container-low/60 p-space-base">
            <div className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-primary">
              <Icone nome="lightbulb" className="text-[16px]" />
              {t("assistente.dica.titulo")}
            </div>
            <p className="mt-space-xs font-body-sm text-body-sm text-outline">
              {t("assistente.dica.texto")}
            </p>
          </div>
        </aside>
      </div>

      {/* ==================== GAVETA DO HISTORICO (mobile) ==================== */}
      {gavetaHistorico && (
        <div
          className="fixed inset-0 z-[90] flex bg-background/80 backdrop-blur-sm lg:hidden"
          role="dialog"
          aria-modal
          aria-label={t("assistente.gaveta.aria")}
          onClick={() => setGavetaHistorico(false)}
        >
          <div
            className="h-full w-[85%] max-w-xs p-space-sm"
            onClick={(evento) => evento.stopPropagation()}
          >
            <PainelHistorico
              entradas={historico.entradas}
              carregando={historico.carregando}
              perguntaAtual={resposta?.pergunta ?? null}
              aoEscolher={(texto) => {
                setPergunta(texto);
                setGavetaHistorico(false);
              }}
              aoLimpar={historico.limpar}
            />
          </div>
        </div>
      )}

      {/* ==================== O CONTEXTO INTEIRO ==================== */}
      <Modal
        aberto={verDados && Boolean(resposta)}
        titulo={t("assistente.modal.titulo")}
        descricao={t("assistente.modal.descricao")}
        aoFechar={() => setVerDados(false)}
      >
        <div className="space-y-space-xs">
          {resposta?.blocos.map((bloco) => (
            <BlocoDeContexto key={bloco.chave} bloco={bloco} />
          ))}
        </div>
      </Modal>
    </>
  );
}

/**
 * A decisao de arquitetura, recolhida.
 *
 * Continua na tela porque explica por que o assistente e assim - foi um teste
 * que decidiu, nao preferencia - mas recolhida, porque quem vem perguntar nao
 * precisa ler isso antes.
 */
function ComoFunciona() {
  const { t } = useTranslation();
  const [aberto, setAberto] = useState(false);

  return (
    <div className="rounded-xl bg-surface-container-low/60">
      <button
        type="button"
        onClick={() => setAberto((atual) => !atual)}
        aria-expanded={aberto}
        className="flex w-full items-center justify-between gap-space-sm rounded-xl px-space-lg py-space-base text-left transition-colors hover:bg-surface-container/40"
      >
        <span className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <Icone nome="account_tree" className="text-[16px]" />
          {t("assistente.comoFunciona.titulo")}
        </span>
        <Icone
          nome={aberto ? "expand_less" : "expand_more"}
          className="text-[20px] text-outline"
        />
      </button>

      {aberto && (
        <div className="space-y-space-base px-space-lg pb-space-lg">
          <div className="grid grid-cols-1 gap-space-base md:grid-cols-3">
            {[
              {
                icone: "search",
                titulo: t("assistente.comoFunciona.passo1Titulo"),
                texto: t("assistente.comoFunciona.passo1Texto"),
              },
              {
                icone: "smart_toy",
                titulo: t("assistente.comoFunciona.passo2Titulo"),
                texto: t("assistente.comoFunciona.passo2Texto"),
              },
              {
                icone: "fact_check",
                titulo: t("assistente.comoFunciona.passo3Titulo"),
                texto: t("assistente.comoFunciona.passo3Texto"),
              },
            ].map((passo) => (
              <div key={passo.titulo} className="rounded-lg bg-surface-container-lowest p-space-base">
                <div className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-primary">
                  <Icone nome={passo.icone} className="text-[16px]" />
                  {passo.titulo}
                </div>
                <p className="mt-space-xs font-body-sm text-body-sm text-on-surface-variant">
                  {passo.texto}
                </p>
              </div>
            ))}
          </div>

          <p className="font-body-sm text-body-sm text-outline">
            {t("assistente.comoFunciona.rodapeParte1")}{" "}
            <code className="text-on-surface-variant">tools</code>{" "}
            {t("assistente.comoFunciona.rodapeParte2")}{" "}
            <code className="text-on-surface-variant">tool_choice: "required"</code>
            {t("assistente.comoFunciona.rodapeParte3")}{" "}
            <strong className="text-error">20.285</strong>{" "}
            {t("assistente.comoFunciona.rodapeParte4")}
          </p>
        </div>
      )}
    </div>
  );
}
