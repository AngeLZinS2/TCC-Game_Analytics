/**
 * Os cartoes de dado estruturado que a resposta pode trazer.
 *
 * Os tres vem de campos do JSON (`blocos`, `recomendacoes`, `jogo_ao_vivo`),
 * decididos no Python - nunca de interpretar o texto que o modelo escreveu.
 * E a regra que sustenta a tela inteira: prosa e prosa, dado e dado.
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import type { BlocoContexto, JogoAoVivo, JogoRecomendado } from "../../api/tipos";
import { Icone, Selo } from "../../componentes/base";
import { ArteJogo } from "../../componentes/CapaJogo";
import { fmtData, fmtMoeda, fmtNumero, fmtPercentual } from "../../utilitarios/formatos";
import { descreverFonte } from "./fontes";

/**
 * Um bloco do contexto, recolhido por padrão.
 *
 * O ícone e o chip dizem a procedência. Não é decoração: o contexto existe para
 * que cada número da resposta possa ser conferido, e conferir um número do
 * banco (consultável de novo, igual) é diferente de conferir um número da loja
 * (lido uma vez, e que muda). Sem a marca, os dois chegariam iguais a quem lê.
 */
export function BlocoDeContexto({ bloco }: { bloco: BlocoContexto }) {
  const [aberto, setAberto] = useState(false);
  const fonte = descreverFonte(bloco.fonte);
  const externa = !fonte.interna;

  return (
    <div
      className={`overflow-hidden rounded bg-surface-container-lowest ${
        externa ? "ring-1 ring-tertiary-container/40" : ""
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
            nome={fonte.icone}
            className={`text-[16px] ${externa ? "text-tertiary" : "text-primary"}`}
          />
          <span className="truncate">{bloco.titulo}</span>
          {externa && (
            <span className="shrink-0 rounded bg-tertiary/10 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-tertiary">
              {fonte.chip}
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
export function CartaoJogoRecomendado({ jogo }: { jogo: JogoRecomendado }) {
  return (
    <Link
      to={`/steam/${jogo.app_id}`}
      className="group flex flex-col overflow-hidden rounded-xl bg-surface-container-lowest ring-1 ring-outline-variant/20 transition-all hover:-translate-y-0.5 hover:ring-primary/50 hover:shadow-lg"
    >
      {/*
        `imagemUrl` só vem preenchida quando o candidato saiu da busca ao vivo
        na loja. Passar `null` no caminho do catálogo é o comportamento certo:
        aí a `ArteJogo` monta a arte pelo `app_id`, como nas outras telas.
      */}
      <ArteJogo
        appId={jogo.app_id}
        nome={jogo.nome}
        imagemUrl={jogo.imagem_header}
        className="h-32 w-full rounded-none"
      />

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
          {/*
            A busca por característica não passa pelas avaliações (seria o
            dobro de chamadas por pergunta), então aqui a nota vem nula. Some
            com o indicador em vez de mostrar um polegar sem número ao lado.
          */}
          {jogo.nota_avaliacoes !== null && (
            <span
              className="flex items-center gap-space-xxs text-tertiary"
              title="Avaliações positivas"
            >
              <Icone nome="thumb_up" className="text-[14px]" />
              {fmtPercentual(jogo.nota_avaliacoes)}
            </span>
          )}
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
export function CartaoJogoAoVivo({ jogo }: { jogo: JogoAoVivo }) {
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
