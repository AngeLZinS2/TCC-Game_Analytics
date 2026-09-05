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
 * - Historico com perguntas de exemplo: nao ha persistencia no servidor, e a
 *   lista comeca vazia de verdade (`assistente/historico.ts`).
 */

import { useMemo, useState } from "react";

import { usePerguntarAssistente, useStatusAssistente, useVisaoGeral } from "../api/consultas";
import type { RespostaAssistente } from "../api/tipos";
import { Icone, MensagemErro } from "../componentes/base";
import { Painel } from "../componentes/hud";
import { Modal } from "../componentes/Modal";
import { AcoesResposta } from "./assistente/AcoesResposta";
import { BlocoDeContexto, CartaoJogoAoVivo, CartaoJogoRecomendado } from "./assistente/cartoes";
import { CartaoResultado } from "./assistente/CartaoResultado";
import { ComoChegamos } from "./assistente/ComoChegamos";
import { Compositor, SUGESTOES } from "./assistente/Compositor";
import { GraficoSerie } from "./assistente/GraficoSerie";
import { useHistoricoAssistente } from "./assistente/historico";
import { CartaoConfianca, PainelFontes } from "./assistente/PainelContexto";
import { PainelHistorico } from "./assistente/PainelHistorico";
import { Processando } from "./assistente/Processando";
import { fmtNumero, fmtRelativo } from "../utilitarios/formatos";

export function AssistenteIAPagina() {
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
    () => SUGESTOES.filter((s) => s.pergunta !== resposta?.pergunta).slice(0, 5),
    [resposta],
  );

  function enviar(texto: string) {
    const limpo = texto.trim();
    if (limpo.length < 3) return;
    setPergunta(limpo);
    historico.registrar(limpo);
    setGavetaHistorico(false);
    assistente.mutate(limpo);
  }

  const utilAtual =
    historico.entradas.find((e) => e.pergunta === resposta?.pergunta)?.util ?? null;

  // Sem chave o resto da tela nao tem o que fazer - e um estado esperado, nao
  // um erro: o projeto inteiro funciona sem provedor externo.
  if (status.data && !status.data.configurado) {
    return (
      <Painel icone="key_off" titulo="Assistente não configurado">
        <p className="font-body-md text-body-md text-on-surface-variant">
          Defina <code className="text-primary">OPENROUTER_API_KEY</code> no{" "}
          <code className="text-primary">.env</code> e reinicie a API. O resto do
          projeto funciona sem isso — o assistente é a única parte que depende de um
          provedor externo.
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
            aria-label="Abrir histórico"
          >
            <Icone nome="history" className="text-[16px]" />
            Histórico
          </button>
          <h1 className="flex items-center gap-space-xs font-headline-sm text-headline-sm uppercase tracking-wide text-primary">
            <span aria-hidden>✦</span> Assistente de Dados
          </h1>
        </div>

        {status.data && (
          <div className="flex flex-wrap items-center gap-space-xs font-badge-status text-badge-status uppercase tracking-wider">
            <span className="flex items-center gap-space-xxs rounded bg-surface-container px-space-sm py-space-xxs text-tertiary">
              <span
                className="h-1.5 w-1.5 rounded-full bg-tertiary shadow-[0_0_6px_rgba(22,239,122,0.8)]"
                aria-hidden
              />
              IA online
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
              Pergunte aos seus dados
            </h2>
            <p className="font-body-sm text-body-sm text-outline">
              Converse com o Nexus e descubra insights reais — do nosso banco e, quando a
              pergunta cita um jogo, da loja da Steam na hora.
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
                Não foi possível analisar os dados
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant">
                Não conseguimos obter uma resposta agora. O contexto sai do nosso banco,
                mas a redação depende de um provedor externo.
              </p>
              <MensagemErro erro={assistente.error} />
              <button
                type="button"
                onClick={() => enviar(pergunta)}
                className="self-start rounded bg-primary-container px-space-base py-space-xs font-title-code text-title-code text-on-primary transition-all hover:brightness-110"
              >
                Tentar novamente
              </button>
            </div>
          )}

          {assistente.isPending && <Processando />}

          {/* ---------- ESTADO VAZIO ---------- */}
          {!resposta && !assistente.isPending && !assistente.isError && (
            <div className="flex flex-col items-center gap-space-sm rounded-xl bg-surface-container-low/60 px-space-lg py-space-3xl text-center">
              <span className="text-[32px] text-primary drop-shadow-[0_0_16px_rgba(0,229,255,0.5)]" aria-hidden>
                ✦
              </span>
              <h3 className="font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
                Seus dados têm respostas
              </h3>
              <p className="max-w-md font-body-sm text-body-sm text-outline">
                Pergunte sobre jogos da Steam, partidas, heróis, preços e as métricas dos
                modelos. {visaoGeral.data && (
                  <>
                    Agora há {fmtNumero(visaoGeral.data.jogos_steam)} jogos e{" "}
                    {fmtNumero(visaoGeral.data.partidas)} partidas no banco.
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
                    Resposta
                  </span>
                  <span className="font-badge-status text-badge-status uppercase tracking-wider text-outline">
                    {fmtNumero(resposta.tokens_entrada)} → {fmtNumero(resposta.tokens_saida)}{" "}
                    tokens
                  </span>
                </div>

                <p className="whitespace-pre-line font-body-lg text-body-lg text-on-surface">
                  {resposta.resposta}
                </p>

                <p className="flex items-start gap-space-xs font-body-sm text-body-sm text-outline">
                  <Icone nome="info" className="mt-[2px] text-[16px] text-primary" />
                  Redigido por <span className="text-on-surface">{resposta.modelo}</span> a
                  partir do contexto ao lado. Se um número não aparece no contexto, ele não
                  deveria aparecer na resposta — confira.
                </p>

                {resposta.fontes_web.length > 0 && (
                  <div className="flex flex-col gap-space-xs border-t border-outline-variant/20 pt-space-base">
                    <span className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-outline">
                      <Icone nome="travel_explore" className="text-[15px]" />
                      Fontes da web (a base não tinha a resposta)
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
                  titulo="Jogo identificado"
                  descricao="Consultado agora na loja da Steam e no IsThereAnyDeal — vale mesmo para um jogo fora do nosso catálogo."
                >
                  <CartaoJogoAoVivo jogo={resposta.jogo_ao_vivo} />
                </Painel>
              )}

              {resposta.recomendacoes.length > 0 && (
                <Painel
                  icone="stadia_controller"
                  titulo="Jogos recomendados"
                  descricao={
                    // A mesma lista sai de dois caminhos diferentes, e dizer o
                    // caminho errado é dizer a procedência errada: "a partir do
                    // catálogo" numa lista que veio da loja afirmaria que esses
                    // jogos são coletados por nós, o que não é verdade.
                    daLoja
                      ? "Buscados na loja da Steam agora, por tag e modo online — não são do nosso catálogo. Ordem: quem tem mais gente jogando neste instante."
                      : "Escolhidos pelo sistema a partir do catálogo — nota de avaliação e popularidade agora, não pelo modelo."
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
                  Continuar explorando
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
              Dica
            </div>
            <p className="mt-space-xs font-body-sm text-body-sm text-outline">
              Cite o nome do jogo na pergunta: o backend busca na loja da Steam na hora,
              mesmo para um jogo que nunca passou pelo nosso coletor.
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
          aria-label="Histórico de perguntas"
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
        titulo="Dados consultados"
        descricao="O contexto exato que o modelo recebeu. O chip FORA DO BANCO marca o que veio da loja da Steam, não da nossa coleta."
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
          Como esta tela funciona
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
                titulo: "1. Recuperação",
                texto:
                  "O backend escolhe os blocos relevantes pela pergunta e os monta com SQL escrito à mão. Não há texto-para-SQL nem consulta gerada pelo modelo.",
              },
              {
                icone: "smart_toy",
                titulo: "2. Redação",
                texto:
                  "O modelo recebe o contexto e a instrução de responder só com ele. Temperatura baixa: a tarefa é reproduzir números, não variar a redação.",
              },
              {
                icone: "fact_check",
                titulo: "3. Verificação",
                texto:
                  "O contexto volta junto da resposta e aparece ao lado. Qualquer número inventado fica visível na hora.",
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
            A primeira tentativa foi dar ferramentas ao modelo e deixá-lo consultar o que
            precisasse. Os modelos gratuitos do OpenRouter ignoram{" "}
            <code className="text-on-surface-variant">tools</code> — e ignoram até{" "}
            <code className="text-on-surface-variant">tool_choice: "required"</code>.
            Perguntado quantos jogos da Steam estavam sendo monitorados, um deles respondeu{" "}
            <strong className="text-error">20.285</strong> sem chamar nada. O número
            verdadeiro é 12. Num projeto cujo propósito é a integridade do dado, isso
            decidiu a arquitetura.
          </p>
        </div>
      )}
    </div>
  );
}
