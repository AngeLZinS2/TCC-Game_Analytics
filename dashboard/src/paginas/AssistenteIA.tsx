/**
 * Assistente de dados.
 *
 * Porte da tela "Assistente de IA" do Stitch.
 *
 * A diferenca em relacao ao mockup e o painel "Dados consultados", que o
 * desenho nao tem. Ele existe porque o modelo de linguagem e o unico componente
 * do projeto capaz de inventar um numero: mostrar exatamente o contexto que ele
 * recebeu transforma cada resposta em algo conferivel sem sair da pagina.
 *
 * O modelo NAO consulta o banco. O backend monta o contexto com SQL escrito a
 * mao e manda junto da pergunta - a tela deixa isso explicito, porque um
 * assistente que parece ter acesso ao banco e um assistente em que se confia
 * demais.
 */

import { useState } from "react";

import { usePerguntarAssistente, useStatusAssistente } from "../api/consultas";
import type { BlocoContexto, RespostaAssistente } from "../api/tipos";
import { Botao, Consulta, Icone, MensagemErro, Selo } from "../componentes/base";
import { Painel, Pilula } from "../componentes/hud";
import { fmtNumero } from "../utilitarios/formatos";

/** Perguntas que exercitam blocos de contexto diferentes. */
const SUGESTOES = [
  "Quantos jogos da Steam estão sendo monitorados?",
  "Qual jogo tem mais jogadores simultâneos e quantos?",
  "Qual herói tem o pior winrate e em quantas partidas?",
  "Qual é a acurácia do modelo de previsão de confronto?",
  "Qual jogo tem a pior recepção nas avaliações?",
  "O Cyberpunk 2077 está no nosso banco? O que a Steam diz dele?",
];

/**
 * Um bloco do contexto, recolhido por padrão.
 *
 * O ícone e o chip dizem a procedência. Não é decoração: o contexto existe para
 * que cada número da resposta possa ser conferido, e conferir um número do
 * banco (consultável de novo, igual) é diferente de conferir um número da loja
 * (lido uma vez, e que muda). Sem a marca, os dois chegariam iguais a quem lê.
 */
function BlocoDeContexto({ bloco }: { bloco: BlocoContexto }) {
  const [aberto, setAberto] = useState(false);
  const daLoja = bloco.fonte === "steam";

  return (
    <div
      className={`overflow-hidden rounded bg-surface-container-lowest ${
        daLoja ? "ring-1 ring-tertiary-container/40" : ""
      }`}
    >
      <button
        type="button"
        onClick={() => setAberto((atual) => !atual)}
        aria-expanded={aberto}
        className="flex w-full items-center justify-between gap-space-sm px-space-md py-space-sm text-left transition-colors hover:bg-surface-container"
      >
        <span className="flex min-w-0 items-center gap-space-xs font-title-code text-title-code text-on-surface">
          <Icone
            nome={daLoja ? "storefront" : "database"}
            className={`text-[16px] ${daLoja ? "text-tertiary" : "text-primary"}`}
          />
          <span className="truncate">{bloco.titulo}</span>
          {daLoja && (
            <span className="shrink-0 rounded bg-tertiary/10 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary">
              fora do banco
            </span>
          )}
        </span>
        <span className="flex items-center gap-space-xs">
          <span className="font-label-caps text-label-caps uppercase text-outline">
            {bloco.conteudo.split("\n").length} linhas
          </span>
          <Icone
            nome={aberto ? "expand_less" : "expand_more"}
            className="text-[18px] text-outline"
          />
        </span>
      </button>

      {aberto && (
        <pre className="rolagem-discreta max-h-64 overflow-auto whitespace-pre-wrap border-t border-outline-variant/30 px-space-md py-space-sm font-body-sm text-body-sm text-on-surface-variant">
          {bloco.conteudo}
        </pre>
      )}
    </div>
  );
}

export function AssistenteIAPagina() {
  const [pergunta, setPergunta] = useState("");
  const status = useStatusAssistente();
  const assistente = usePerguntarAssistente();

  const resposta: RespostaAssistente | undefined = assistente.data;

  function enviar(texto: string) {
    const limpo = texto.trim();
    if (limpo.length < 3) return;
    setPergunta(limpo);
    assistente.mutate(limpo);
  }

  return (
    <>
      {/* ==================== CABECALHO ==================== */}
      <section className="flex flex-col gap-space-base pt-space-base lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-space-xs">
          <div className="flex flex-wrap items-center gap-space-sm">
            <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-primary drop-shadow-[0_0_12px_rgba(0,229,255,0.4)]">
              Assistente de Dados
            </h1>
            <Selo cor="primario">LLM</Selo>
            <span className="hidden font-label-caps text-label-caps uppercase tracking-wider text-outline sm:inline">
              ML // Deck 08
            </span>
          </div>

          <p className="font-body-sm text-body-sm text-on-surface-variant">
            Perguntas em português sobre jogos e esports. O modelo{" "}
            <strong>não consulta nada sozinho</strong>: o backend monta o contexto —
            do nosso banco e, quando a pergunta cita um jogo, da loja da Steam na
            hora — e manda junto da pergunta. O contexto vem na resposta, com a
            fonte de cada bloco, para todo número poder ser conferido.
          </p>
        </div>

        {status.data && (
          <div className="flex flex-wrap items-center gap-space-xs">
            <Selo cor={status.data.configurado ? "positivo" : "negativo"}>
              {status.data.configurado ? "Configurado" : "Sem chave"}
            </Selo>
            <span className="font-title-code text-title-code text-outline">
              {status.data.provedor} · {status.data.modelo}
            </span>
          </div>
        )}
      </section>

      {status.data && !status.data.configurado ? (
        <Painel icone="key_off" titulo="Assistente não configurado">
          <p className="font-body-md text-body-md text-on-surface-variant">
            Defina <code className="text-primary">OPENROUTER_API_KEY</code> no{" "}
            <code className="text-primary">.env</code> e reinicie a API. O resto do
            projeto funciona sem isso — o assistente é a única parte que depende de um
            provedor externo.
          </p>
        </Painel>
      ) : (
        <>
          {/* ==================== PERGUNTA ==================== */}
          <Painel
            icone="smart_toy"
            titulo="Pergunte sobre os dados"
            descricao="Volumes coletados, catálogo da Steam, partidas, heróis, avaliações e as métricas dos modelos."
          >
            <div className="flex flex-col gap-space-sm sm:flex-row">
              <input
                type="text"
                value={pergunta}
                onChange={(evento) => setPergunta(evento.target.value)}
                onKeyDown={(evento) => {
                  if (evento.key === "Enter") enviar(pergunta);
                }}
                placeholder="Ex.: qual herói tem o melhor winrate?"
                aria-label="Pergunta"
                className="flex-1 rounded bg-surface-container-lowest px-space-md py-space-sm font-body-md text-body-md text-on-surface shadow-inner placeholder:text-outline focus:bg-surface-container focus:outline-none"
              />
              <Botao
                icone="send"
                variante="primario"
                aoClicar={() => enviar(pergunta)}
                desabilitado={assistente.isPending || pergunta.trim().length < 3}
              >
                {assistente.isPending ? "Consultando…" : "Perguntar"}
              </Botao>
            </div>

            <div className="flex flex-wrap gap-space-xs">
              {SUGESTOES.map((sugestao) => (
                <Pilula
                  key={sugestao}
                  desabilitada={assistente.isPending}
                  aoClicar={() => enviar(sugestao)}
                >
                  {sugestao}
                </Pilula>
              ))}
            </div>
          </Painel>

          {assistente.isError && <MensagemErro erro={assistente.error} />}

          {assistente.isPending && (
            <Painel icone="hourglass_top" titulo="Consultando o modelo">
              <div className="h-24 animate-pulse rounded bg-surface-container-high/60" />
              <p className="font-body-sm text-body-sm text-outline">
                O contexto já foi montado a partir do banco; o que demora é a resposta do
                provedor.
              </p>
            </Painel>
          )}

          {/* ==================== RESPOSTA + CONTEXTO ==================== */}
          {resposta && !assistente.isPending && (
            <section className="grid grid-cols-1 gap-space-base xl:grid-cols-3">
              <Painel
                icone="chat"
                titulo="Resposta"
                descricao={resposta.pergunta}
                className="xl:col-span-2"
                meta={
                  <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                    {fmtNumero(resposta.tokens_entrada)} →{" "}
                    {fmtNumero(resposta.tokens_saida)} tokens
                  </span>
                }
              >
                <p className="whitespace-pre-line font-body-lg text-body-lg text-on-surface">
                  {resposta.resposta}
                </p>

                <p className="flex items-start gap-space-xs border-t border-outline-variant/30 pt-space-sm font-body-sm text-body-sm text-outline">
                  <Icone nome="info" className="mt-[2px] text-[16px] text-primary" />
                  Gerado por <span className="text-on-surface">{resposta.modelo}</span> a
                  partir dos blocos ao lado. Se um número não aparece no contexto, ele não
                  deveria aparecer na resposta — confira.
                </p>
              </Painel>

              <Painel
                icone="database"
                titulo="Dados consultados"
                descricao="O contexto exato que o modelo recebeu. O chip FORA DO BANCO marca o que veio da loja da Steam, não da nossa coleta."
                meta={<Selo>{resposta.blocos.length} blocos</Selo>}
              >
                <div className="space-y-space-xs">
                  {resposta.blocos.map((bloco) => (
                    <BlocoDeContexto key={bloco.chave} bloco={bloco} />
                  ))}
                </div>
              </Painel>
            </section>
          )}

          {/* ==================== COMO FUNCIONA ==================== */}
          <Painel
            icone="account_tree"
            titulo="Como esta tela funciona"
            descricao="A arquitetura foi decidida por um teste, não por preferência."
          >
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
                <div
                  key={passo.titulo}
                  className="rounded-lg bg-surface-container-lowest p-space-base"
                >
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
              A primeira tentativa foi dar ferramentas ao modelo e deixá-lo consultar o
              que precisasse. Os modelos gratuitos do OpenRouter ignoram{" "}
              <code className="text-on-surface-variant">tools</code> — e ignoram até{" "}
              <code className="text-on-surface-variant">tool_choice: "required"</code>.
              Perguntado quantos jogos da Steam estavam sendo monitorados, um deles
              respondeu <strong className="text-error">20.285</strong> sem chamar nada. O
              número verdadeiro é 12. Num projeto cujo propósito é a integridade do dado,
              isso decidiu a arquitetura.
            </p>
          </Painel>
        </>
      )}

      {status.isError && (
        <Consulta estado={status} altura={120}>
          {() => null}
        </Consulta>
      )}
    </>
  );
}
