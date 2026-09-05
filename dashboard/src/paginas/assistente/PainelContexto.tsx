/**
 * A lateral direita: de onde veio a resposta e o quanto ela se sustenta.
 *
 * Duas regras moldaram este arquivo:
 *
 * 1. Os numeros das fontes sao os de `/api/visao-geral` e os dos proprios
 *    blocos que voltaram na resposta. Nao ha contagem estimada.
 *
 * 2. O backend NAO devolve `confidence`. O desenho mostrava "92% - alta
 *    confianca", e um numero desses so poderia sair daqui inventado. Entao a
 *    confianca e qualitativa e diz EM CIMA DE QUE ela foi classificada:
 *    quantos blocos, quantos pontos comparaveis, ha quanto tempo o dado foi
 *    coletado. Se um dia o backend mandar um score, `nivel` passa a vir dele
 *    e o resto da tela nao muda.
 */

import type { RespostaAssistente, VisaoGeral } from "../../api/tipos";
import { Icone } from "../../componentes/base";
import { fmtNumero, fmtRelativo } from "../../utilitarios/formatos";

/** Uma linha do painel de fontes: rotulo, numero real, icone. */
function LinhaFonte({
  icone,
  rotulo,
  valor,
}: {
  icone: string;
  rotulo: string;
  valor: string;
}) {
  return (
    <li className="flex items-start gap-space-sm border-b border-outline-variant/20 py-space-sm last:border-0">
      <Icone nome={icone} className="mt-[2px] text-[18px] text-primary" />
      <div className="min-w-0">
        <div className="truncate font-title-code text-title-code text-on-surface">{rotulo}</div>
        <div className="font-badge-status text-badge-status uppercase tracking-wider text-outline">
          {valor}
        </div>
      </div>
    </li>
  );
}

export function PainelFontes({
  resposta,
  visaoGeral,
  aoVerDados,
}: {
  resposta: RespostaAssistente | undefined;
  visaoGeral: VisaoGeral | undefined;
  aoVerDados: () => void;
}) {
  // Sem resposta ainda, o painel mostra o que EXISTE no banco - e informacao
  // util (dimensiona o que da para perguntar), nao um placeholder.
  const ultimaColeta = visaoGeral?.coletas
    .map((c) => c.ultima_coleta)
    .filter((data): data is string => Boolean(data))
    .sort()
    .at(-1);

  return (
    <section className="rounded-xl bg-surface-container-low/90 p-space-base shadow-2xl">
      <h2 className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
        {resposta ? "Contexto da resposta" : "Dados disponíveis"}
      </h2>

      <ul className="mt-space-sm flex flex-col">
        {resposta ? (
          resposta.blocos.map((bloco) => (
            <LinhaFonte
              key={bloco.chave}
              icone={bloco.fonte === "steam" ? "storefront" : "database"}
              rotulo={bloco.titulo}
              valor={`${bloco.conteudo.split("\n").length} linhas · ${
                bloco.fonte === "steam" ? "loja, agora" : "nosso banco"
              }`}
            />
          ))
        ) : (
          <>
            <LinhaFonte
              icone="stadia_controller"
              rotulo="Jogos da Steam"
              valor={`${fmtNumero(visaoGeral?.jogos_steam)} no catálogo`}
            />
            <LinhaFonte
              icone="swords"
              rotulo="Partidas"
              valor={`${fmtNumero(visaoGeral?.partidas)} coletadas`}
            />
            <LinhaFonte
              icone="person"
              rotulo="Personagens"
              valor={`${fmtNumero(visaoGeral?.personagens)} registrados`}
            />
          </>
        )}

        {ultimaColeta && (
          <LinhaFonte
            icone="schedule"
            rotulo="Última coleta"
            valor={fmtRelativo(ultimaColeta)}
          />
        )}
      </ul>

      {resposta && (
        <button
          type="button"
          onClick={aoVerDados}
          className="mt-space-sm flex w-full items-center justify-center gap-space-xs rounded bg-surface-container px-space-sm py-space-xs font-title-code text-title-code text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-primary"
        >
          Ver todas as fontes
          <Icone nome="unfold_more" className="text-[14px]" />
        </button>
      )}
    </section>
  );
}

/** Como a confianca foi classificada, e com base em que fato. */
interface Criterio {
  atendido: boolean;
  texto: string;
}

function criteriosDe(resposta: RespostaAssistente): Criterio[] {
  const linhas = resposta.blocos.reduce(
    (soma, b) => soma + b.conteudo.split("\n").length,
    0,
  );
  const pontos = resposta.series.reduce((soma, s) => soma + s.itens.length, 0);

  return [
    {
      atendido: resposta.blocos.length >= 2,
      texto: `${resposta.blocos.length} ${
        resposta.blocos.length === 1 ? "bloco" : "blocos"
      } de contexto`,
    },
    {
      atendido: linhas >= 10,
      texto: `${fmtNumero(linhas)} linhas consultadas`,
    },
    {
      atendido: pontos > 0,
      texto: pontos > 0 ? `${pontos} valores comparáveis` : "nada comparável numericamente",
    },
  ];
}

export function CartaoConfianca({ resposta }: { resposta: RespostaAssistente }) {
  const criterios = criteriosDe(resposta);
  const atendidos = criterios.filter((c) => c.atendido).length;
  const alta = atendidos === criterios.length;
  const limitada = atendidos <= 1;

  const nivel = alta ? "Base sólida" : limitada ? "Base limitada" : "Base parcial";
  const cor = alta ? "text-tertiary" : limitada ? "text-error" : "text-primary";

  return (
    <section className="rounded-xl bg-surface-container-low/90 p-space-base shadow-2xl">
      <h2 className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
        Base da resposta
      </h2>

      <div className={`mt-space-sm flex items-center gap-space-xs ${cor}`}>
        <Icone
          nome={alta ? "verified" : limitada ? "warning" : "info"}
          className="text-[22px]"
        />
        <span className="font-headline-sm text-headline-sm">{nivel}</span>
      </div>

      <ul className="mt-space-sm flex flex-col gap-space-xs">
        {criterios.map((criterio) => (
          <li
            key={criterio.texto}
            className="flex items-start gap-space-xs font-body-sm text-body-sm text-on-surface-variant"
          >
            <Icone
              nome={criterio.atendido ? "check" : "remove"}
              className={`mt-[2px] text-[14px] ${
                criterio.atendido ? "text-tertiary" : "text-outline"
              }`}
            />
            {criterio.texto}
          </li>
        ))}
      </ul>

      {/*
        A nota abaixo nao e rodape decorativo: sem ela, "Base sólida" seria
        lido como um score do modelo. E o oposto - a classificacao mede o
        contexto, e o modelo continua sendo a parte que pode errar.
      */}
      <p className="mt-space-sm border-t border-outline-variant/20 pt-space-sm font-body-sm text-body-sm text-outline">
        Classificação do <strong>contexto</strong>, não da redação. O provedor não
        devolve grau de confiança — o que dá para medir aqui é o quanto de dado real
        sustentou a resposta.
      </p>
    </section>
  );
}
