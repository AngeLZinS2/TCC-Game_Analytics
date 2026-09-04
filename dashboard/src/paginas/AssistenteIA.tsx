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
import { Link } from "react-router-dom";

import { usePerguntarAssistente, useStatusAssistente } from "../api/consultas";
import type {
  BlocoContexto,
  JogoAoVivo,
  JogoRecomendado,
  RespostaAssistente,
} from "../api/tipos";
import { Botao, Consulta, Icone, MensagemErro, Selo } from "../componentes/base";
import { ArteJogo } from "../componentes/CapaJogo";
import { Painel, Pilula } from "../componentes/hud";
import { fmtData, fmtMoeda, fmtNumero, fmtPercentual } from "../utilitarios/formatos";

/** Perguntas que exercitam blocos de contexto diferentes. */
const SUGESTOES = [
  "Que jogo de ação você recomenda?",
  "Quantos jogos da Steam estão sendo monitorados?",
  "Qual jogo tem mais jogadores simultâneos e quantos?",
  "Qual herói tem o pior winrate e em quantas partidas?",
  "Qual é a acurácia do modelo de previsão de confronto?",
  "Qual jogo tem a pior recepção nas avaliações?",
  "O Cyberpunk 2077 está no nosso banco? O que a Steam diz dele?",
  "Onde encontro o Helldivers 2 pelo menor preço?",
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

/**
 * O cartão de um jogo recomendado - imagem, gêneros e os três números que
 * justificam a escolha, em vez de exigir que quem lê procure isso no texto.
 *
 * `jogo` vem de `resposta.recomendacoes`, não de interpretar a resposta do
 * modelo: é o Python (`ml.assistente._recomendacoes`) quem decide o ranking,
 * então o cartão mostra exatamente o candidato que o sistema escolheu, nunca
 * um jogo que o texto livre "pareceu" estar recomendando.
 */
function CartaoJogoRecomendado({ jogo }: { jogo: JogoRecomendado }) {
  return (
    <Link
      to={`/steam/${jogo.app_id}`}
      className="group flex flex-col overflow-hidden rounded-xl bg-surface-container-lowest ring-1 ring-outline-variant/20 transition-all hover:-translate-y-0.5 hover:ring-primary/50 hover:shadow-lg"
    >
      <ArteJogo appId={jogo.app_id} nome={jogo.nome} className="h-32 w-full rounded-none" />

      <div className="flex flex-1 flex-col gap-space-sm p-space-base">
        <h3 className="font-headline-sm text-headline-sm text-on-surface transition-colors group-hover:text-primary">
          {jogo.nome}
        </h3>

        {jogo.generos.length > 0 && (
          <div className="flex flex-wrap gap-space-xxs">
            {jogo.generos.slice(0, 3).map((genero) => (
              <Selo key={genero}>{genero}</Selo>
            ))}
          </div>
        )}

        <div className="mt-auto flex items-center justify-between gap-space-xs border-t border-outline-variant/20 pt-space-sm font-title-code text-title-code">
          <span
            className="flex items-center gap-space-xxs text-tertiary"
            title="Avaliações positivas"
          >
            <Icone nome="thumb_up" className="text-[14px]" />
            {fmtPercentual(jogo.nota_avaliacoes)}
          </span>
          <span
            className="flex items-center gap-space-xxs text-on-surface-variant"
            title="Jogadores simultâneos agora"
          >
            <Icone nome="groups" className="text-[14px]" />
            {fmtNumero(jogo.jogadores_simultaneos)}
          </span>
          <span className="text-primary-container">
            {jogo.gratuito ? "Gratuito" : fmtMoeda(jogo.preco, jogo.moeda)}
          </span>
        </div>
      </div>
    </Link>
  );
}

/**
 * O banner de um jogo identificado ao vivo - a resposta a "traga tudo mesmo
 * não estando no snapshot": imagem real (`imagem_header`, direto do
 * `appdetails` da Steam) e comparação de preço buscada na hora via
 * IsThereAnyDeal, iguais às da ficha de um jogo do catálogo - só que para um
 * jogo que pode nunca ter passado pelo nosso coletor.
 *
 * `jogo` vem de `resposta.jogo_ao_vivo` (estruturado, decidido em Python), não
 * de interpretar o texto do modelo - mesmo motivo de `CartaoJogoRecomendado`.
 */
function CartaoJogoAoVivo({ jogo }: { jogo: JogoAoVivo }) {
  const ofertas = jogo.ofertas;
  const maisBarata = ofertas[0];

  return (
    <div className="overflow-hidden rounded-xl bg-surface-container-lowest ring-1 ring-tertiary-container/30">
      {/*
        Fundo borrado + capa nítida por cima, em vez de uma imagem só esticada
        na largura toda. A capa da Steam tem 460x215 e fica pixelada se
        crescer além disso; a arte de fundo é grande, mas em vários jogos a
        própria Valve já entrega escurecida e borrada (Call of Duty) enquanto
        em outros vem viva (Helldivers). Cada uma no papel em que funciona:
        a de fundo preenche a largura, a capa fica nítida no tamanho nativo.
      */}
      <div className="relative flex items-center justify-center overflow-hidden bg-surface-container-high px-space-base py-space-lg">
        {jogo.imagem_fundo && (
          <>
            <div
              className="absolute inset-0 scale-110 bg-cover bg-center opacity-60 blur-md"
              style={{ backgroundImage: `url(${jogo.imagem_fundo})` }}
              aria-hidden
            />
            <div
              className="absolute inset-0 bg-gradient-to-t from-surface-container-lowest/90 to-transparent"
              aria-hidden
            />
          </>
        )}

        <ArteJogo
          appId={jogo.app_id}
          nome={jogo.nome}
          imagemUrl={jogo.imagem_header}
          className="relative h-auto max-h-[215px] w-full max-w-[460px] shadow-2xl"
        />
      </div>

      <div className="flex flex-col gap-space-base p-space-base">
        <div className="flex flex-wrap items-start justify-between gap-space-sm">
          <div>
            <h3 className="font-headline-sm text-headline-sm text-on-surface">{jogo.nome}</h3>
            {jogo.desenvolvedora && (
              <p className="font-title-code text-title-code text-outline">
                {jogo.desenvolvedora}
              </p>
            )}
          </div>
          <span
            className={`rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase ${
              jogo.no_nosso_banco
                ? "bg-primary-container/15 text-primary-container"
                : "bg-surface-container-highest text-outline"
            }`}
          >
            {jogo.no_nosso_banco ? "no nosso catálogo" : "consultado agora, fora do catálogo"}
          </span>
        </div>

        {jogo.generos.length > 0 && (
          <div className="flex flex-wrap gap-space-xxs">
            {jogo.generos.map((genero) => (
              <Selo key={genero}>{genero}</Selo>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 gap-space-sm rounded-lg bg-surface-container p-space-base sm:grid-cols-2">
          <div>
            <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              Preço na Steam
            </div>
            <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-on-surface">
              {jogo.gratuito ? "Gratuito" : fmtMoeda(jogo.preco_atual, jogo.moeda)}
            </div>
          </div>
          {maisBarata && (
            <div>
              <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                Melhor preço agora
              </div>
              <div className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none text-tertiary-container">
                {fmtMoeda(maisBarata.preco, maisBarata.moeda)}
              </div>
              <div className="font-title-code text-title-code text-on-surface-variant">
                na {maisBarata.loja}
              </div>
            </div>
          )}
        </div>

        {ofertas.length > 0 && (
          <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                  <th className="px-space-md py-space-xs">Loja</th>
                  <th className="px-space-md py-space-xs text-right">Preço</th>
                  <th className="px-space-md py-space-xs" />
                </tr>
              </thead>
              <tbody className="font-body-sm text-body-sm">
                {ofertas.map((o, i) => (
                  <tr key={o.loja + i} className={i % 2 ? "bg-surface-container/40" : ""}>
                    <td className="px-space-md py-space-xs text-on-surface">
                      {o.loja}
                      {o.melhor && (
                        <span className="ml-space-xs rounded bg-tertiary/10 px-space-xxs py-[1px] font-badge-status text-badge-status uppercase text-tertiary">
                          melhor
                        </span>
                      )}
                    </td>
                    <td className="px-space-md py-space-xs text-right font-title-code text-title-code tabular-nums text-on-surface">
                      {fmtMoeda(o.preco, o.moeda)}
                    </td>
                    <td className="px-space-md py-space-xs text-right">
                      {o.url && (
                        <a
                          href={o.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-space-xxs font-title-code text-title-code text-primary hover:underline"
                        >
                          abrir <Icone nome="open_in_new" className="text-[13px]" />
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {jogo.menor_historico && (
          <p className="font-body-sm text-body-sm text-on-surface-variant">
            Já custou{" "}
            <strong className="text-tertiary-container">
              {fmtMoeda(jogo.menor_historico.preco, jogo.menor_historico.moeda)}
            </strong>
            {jogo.menor_historico.loja && ` na ${jogo.menor_historico.loja}`}
            {jogo.menor_historico.data && ` (${fmtData(jogo.menor_historico.data)})`} — o menor
            preço já registrado (IsThereAnyDeal).
          </p>
        )}

        <div className="flex flex-wrap gap-space-sm border-t border-outline-variant/20 pt-space-sm">
          {jogo.no_nosso_banco && (
            <Link
              to={`/steam/${jogo.app_id}`}
              className="inline-flex items-center gap-space-xxs font-title-code text-title-code text-primary hover:underline"
            >
              Ver ficha completa <Icone nome="arrow_forward" className="text-[14px]" />
            </Link>
          )}
          <a
            href={`https://store.steampowered.com/app/${jogo.app_id}`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-space-xxs font-title-code text-title-code text-on-surface-variant hover:text-primary hover:underline"
          >
            Página na Steam <Icone nome="open_in_new" className="text-[13px]" />
          </a>
        </div>
      </div>
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

          {/* ==================== JOGO IDENTIFICADO AO VIVO ==================== */}
          {resposta && !assistente.isPending && resposta.jogo_ao_vivo && (
            <Painel
              icone="storefront"
              titulo="Jogo identificado"
              descricao="Consultado agora na loja da Steam e no IsThereAnyDeal — vale mesmo para um jogo fora do nosso catálogo."
            >
              <CartaoJogoAoVivo jogo={resposta.jogo_ao_vivo} />
            </Painel>
          )}

          {/* ==================== JOGOS RECOMENDADOS ==================== */}
          {resposta && !assistente.isPending && resposta.recomendacoes.length > 0 && (
            <Painel
              icone="stadia_controller"
              titulo="Jogos recomendados"
              descricao="Escolhidos pelo sistema a partir do catálogo — nota de avaliação e popularidade agora, não pelo modelo."
            >
              <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2 lg:grid-cols-3">
                {resposta.recomendacoes.map((jogo) => (
                  <CartaoJogoRecomendado key={jogo.app_id} jogo={jogo} />
                ))}
              </div>
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
