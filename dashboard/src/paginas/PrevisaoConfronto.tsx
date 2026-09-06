/**
 * Previsao de confronto: qual time tem mais chance de vencer, e por que.
 *
 * E a pergunta que se faz ANTES da partida - a unica previsao de partida que o
 * projeto serve hoje.
 *
 * A agenda e um kanban por dia: calendario e naturalmente uma sequencia de
 * dias, e uma tabela unica obriga a ler a coluna de data para saber quando cada
 * jogo acontece. Clicar num card abre o detalhe.
 *
 * O detalhe e UM componente (`DetalheConfronto`), montado em dois lugares: no
 * modal do kanban e na secao de confronto hipotetico. Duas implementacoes do
 * mesmo "por que" divergiriam na primeira vez que uma delas mudasse.
 *
 * O aviso de validacao no topo nao e decoracao. Com 71 confrontos coletados a
 * validacao temporal nao mostra o modelo superando a taxa base - e uma tela que
 * exibe "78% de chance" sem dizer isso convence de algo que os dados ainda nao
 * sustentam.
 */

import { useEffect, useMemo, useState } from "react";

import { useEntrarNaTela } from "../hooks/animacao";
import {
  useAgendaConfronto,
  useLigasConfronto,
  usePrevisaoConfronto,
  useRankingConfronto,
  useRelatorioConfronto,
} from "../api/consultas";
import type {
  ConfrontoAgendado,
  ContribuicaoConfronto,
  EquipeConfronto,
  FatorConfronto,
  LigaConfronto,
  PrevisaoConfronto as TipoPrevisao,
  PrioExternoConfronto,
  RelatorioConfronto,
  ValidacaoConfronto,
} from "../api/tipos";
import { Consulta, Esqueleto, Icone, MensagemErro, Selo } from "../componentes/base";
import { BarraDivergente, BarraSegmentada, CAMPO, Painel, Pilula } from "../componentes/hud";
import { Modal } from "../componentes/Modal";
import { SeletorDeJogo } from "../componentes/SeletorDeJogo";
import { useJogoAtual } from "../layout/JogoAtual";
import { PALETA_POLOS, TOKENS } from "../tema";
import {
  fmtDataCurta,
  fmtDataHora,
  fmtDecimal,
  fmtNumero,
  fmtPercentual,
} from "../utilitarios/formatos";

/** Quantos dias o kanban mostra. Além disso a agenda vira especulação. */
const DIAS_NO_KANBAN = 5;

/**
 * O rótulo de um lado do confronto.
 *
 * "(Radiant)"/"(Dire)" só faz sentido em Dota 2 — é a nomenclatura da própria
 * OpenDota para os dois lados do mapa. Antes de a Previsão de Confronto
 * atender outros jogos, o rótulo vinha fixo com o parêntese; numa tela de
 * Counter-Strike ele apareceria do mesmo jeito, como se a partida tivesse
 * lados chamados Radiant e Dire — o que não existe fora do Dota.
 */
function rotuloDoLado(jogo: string, lado: "a" | "b"): string {
  const base = lado === "a" ? "Lado A" : "Lado B";
  if (jogo !== "dota2") return base;
  return lado === "a" ? `${base} (Radiant)` : `${base} (Dire)`;
}

/** O aviso de confiabilidade. Aparece sempre, com o tom que os números pedem. */
function AvisoValidacao({ validacao }: { validacao: ValidacaoConfronto }) {
  if (!validacao.suficiente) {
    return (
      <div className="flex items-start gap-space-sm rounded-xl border border-outline-variant/40 bg-surface-container-low/60 px-space-lg py-space-base">
        <Icone nome="info" className="mt-[2px] text-[18px] text-outline" />
        <p className="font-body-md text-body-md text-on-surface-variant">
          {validacao.motivo}
        </p>
      </div>
    );
  }

  const superaBase = (validacao.acuracia ?? 0) > (validacao.taxa_base ?? 0);

  return (
    <div
      className="flex items-start gap-space-sm rounded-xl px-space-lg py-space-base"
      style={{
        border: `1px solid ${superaBase ? PALETA_POLOS.positivo : PALETA_POLOS.negativo}55`,
        background: `${superaBase ? PALETA_POLOS.positivo : PALETA_POLOS.negativo}0d`,
      }}
    >
      <Icone nome={superaBase ? "verified" : "warning"} className="mt-[2px] text-[18px]" />
      <div className="font-body-md text-body-md text-on-surface-variant">
        <strong className="text-on-surface">
          Validação temporal em {validacao.avaliadas} partidas:{" "}
          {fmtPercentual((validacao.acuracia ?? 0) * 100)} de acerto (±
          {fmtPercentual((validacao.margem_erro ?? 0) * 100)}), contra uma taxa base de{" "}
          {fmtPercentual((validacao.taxa_base ?? 0) * 100)}.
        </strong>{" "}
        {superaBase ? (
          <>
            O modelo supera o chute, mas a margem de erro ainda é larga — mais partidas
            estreitam o intervalo.
          </>
        ) : (
          <>
            <span style={{ color: PALETA_POLOS.negativo }}>
              Com esta amostra o modelo ainda não demonstrou poder preditivo:
            </span>{" "}
            acertar sempre no lado mais frequente daria o mesmo resultado. O ROC-AUC de{" "}
            {fmtDecimal(validacao.roc_auc ?? 0, 3)} sugere algum sinal na ordenação, mas{" "}
            {validacao.avaliadas} partidas não decidem isso. Leia as probabilidades como{" "}
            <strong className="text-on-surface">uma leitura do histórico</strong>, não como
            uma aposta validada. O que muda esse quadro é coletar mais partidas.
          </>
        )}
      </div>
    </div>
  );
}

/** Um lado do confronto: escudo, nome, cartel e a probabilidade. */
function LadoDoConfronto({
  equipe,
  probabilidade,
  cor,
  rotuloLado,
}: {
  equipe: EquipeConfronto;
  probabilidade: number;
  cor: string;
  rotuloLado: string;
}) {
  return (
    <div className="flex flex-1 flex-col items-center gap-space-sm text-center">
      <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
        {rotuloLado}
      </span>

      {equipe.logo_url ? (
        <img
          src={equipe.logo_url}
          alt=""
          className="h-16 w-16 rounded object-contain"
          onError={(evento) => {
            evento.currentTarget.style.display = "none";
          }}
        />
      ) : (
        <div className="flex h-16 w-16 items-center justify-center rounded bg-surface-container-high font-headline-md text-headline-md text-outline">
          {equipe.nome.charAt(0).toUpperCase()}
        </div>
      )}

      <div className="min-w-0">
        <div className="truncate font-headline-md text-headline-md text-on-surface">
          {equipe.nome}
        </div>
        <div className="font-title-code text-title-code text-outline">
          {equipe.vitorias}/{equipe.partidas} · {fmtPercentual(equipe.winrate)}
        </div>
        {equipe.posicao_ranking !== null && (
          <div
            className="mt-space-xxs inline-flex items-center gap-1 rounded-full bg-surface-container-high px-2 py-[1px] font-title-code text-title-code text-on-surface-variant"
            title={
              equipe.pontos_ranking !== null
                ? `${equipe.pontos_ranking} pontos no Regional Standings da Valve`
                : "Regional Standings da Valve"
            }
          >
            <Icone nome="social_leaderboard" className="text-[13px] text-primary" />
            #{equipe.posicao_ranking} Valve
          </div>
        )}
      </div>

      <div
        className="font-display-hero text-display-hero leading-none tracking-tight"
        style={{ color: cor }}
      >
        {fmtPercentual(probabilidade * 100)}
      </div>
    </div>
  );
}

/**
 * Badge compacto de confiabilidade, dentro do proprio modal.
 *
 * O paragrafo inteiro (por que supera ou nao a taxa base) ja mora na faixa do
 * topo da pagina (`AvisoValidacao`) - repetir o texto aqui, dentro de CADA
 * modal, cansaria quem abre confronto atras de confronto no kanban. O badge
 * da o mesmo veredito num relance, com o numero que sustenta ele no `title`.
 */
function BadgeConfianca({ validacao }: { validacao: ValidacaoConfronto }) {
  if (!validacao.suficiente) {
    return (
      <span className="inline-flex items-center gap-space-xs rounded-full bg-surface-container px-space-md py-space-xs font-badge-status text-badge-status uppercase tracking-widest text-outline">
        <Icone nome="help" className="text-[14px]" />
        Amostra curta · {validacao.avaliadas} partidas
      </span>
    );
  }

  const superaBase = (validacao.acuracia ?? 0) > (validacao.taxa_base ?? 0);
  const cor = superaBase ? PALETA_POLOS.positivo : PALETA_POLOS.negativo;

  return (
    <span
      className="inline-flex items-center gap-space-xs rounded-full px-space-md py-space-xs font-badge-status text-badge-status uppercase tracking-widest"
      style={{ color: cor, background: `${cor}1a` }}
      title={`ROC-AUC ${fmtDecimal(validacao.roc_auc ?? 0, 3)} sobre ${validacao.avaliadas} partidas de teste, taxa base ${fmtPercentual((validacao.taxa_base ?? 0) * 100, 0)}`}
    >
      <Icone nome={superaBase ? "verified" : "warning"} className="text-[14px]" />
      {superaBase ? "Supera o chute" : "Sem poder preditivo"} ·{" "}
      {fmtPercentual((validacao.acuracia ?? 0) * 100, 0)}
    </span>
  );
}

/** Icone de cada fator, por rotulo. Decoracao — nunca a unica pista do que e. */
function iconeDoFator(rotulo: string): string {
  if (rotulo.startsWith("Força")) return "bolt";
  if (rotulo.startsWith("Winrate")) return "trending_up";
  if (rotulo.startsWith("Partidas")) return "table_rows";
  if (rotulo.startsWith("Saldo")) return "swap_vert";
  if (rotulo.startsWith("Ouro")) return "payments";
  if (rotulo.startsWith("Experiência")) return "auto_awesome";
  if (rotulo.startsWith("KDA")) return "swords";
  if (rotulo.startsWith("Duração")) return "schedule";
  return "insights";
}

/**
 * A fracao do lado A na barra proporcional de um fator.
 *
 * Barra proporcional, nao gradiente fixo: a largura de cada lado e a fatia
 * dele no total, entao a diferenca entre "588 x 452" e "9,69 x 2,13" aparece
 * na hora. Os valores sao deslocados para nao-negativo antes da divisao
 * porque a forca vai a numeros negativos, e uma fracao com denominador que
 * muda de sinal nao significa nada.
 */
function fracaoDoFator(fator: FatorConfronto): number {
  const a = fator.valor_a ?? 0;
  const b = fator.valor_b ?? 0;
  const piso = Math.min(0, a, b);
  const total = a - piso + (b - piso);
  return total > 0 ? (a - piso) / total : 0.5;
}

/**
 * Um fator do "por que", como cartao de HUD — nao como linha de tabela.
 *
 * Os numeros sao exatamente os que a API ja mandava; o que muda e a
 * apresentacao, para casar com o resto do desenho: cartao com brilho no
 * canto quando o fator pesa na conta, icone, e a mesma barra proporcional de
 * antes.
 */
function CartaoFator({
  fator,
  nomeA,
  nomeB,
}: {
  fator: FatorConfronto;
  nomeA: string;
  nomeB: string;
}) {
  const indefinido = fator.valor_a === null || fator.valor_b === null;
  const favoreceA = (fator.diferenca ?? 0) > 0;
  const fracaoA = fracaoDoFator(fator);

  return (
    <div className="relative overflow-hidden rounded-xl bg-surface-container p-space-base">
      {fator.peso_no_modelo && (
        <div
          className="pointer-events-none absolute right-0 top-0 h-20 w-20 rounded-full bg-primary-container/10 blur-2xl"
          aria-hidden
        />
      )}

      <div className="flex items-center justify-between gap-space-xs">
        <span className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-outline">
          <Icone
            nome={iconeDoFator(fator.rotulo)}
            className={`text-[16px] ${fator.peso_no_modelo ? "text-primary" : ""}`}
          />
          {fator.rotulo}
        </span>
        {fator.peso_no_modelo && (
          <span className="shrink-0 rounded bg-primary/10 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase text-primary">
            entra na conta
          </span>
        )}
      </div>

      <div className="mt-space-sm flex items-start justify-between gap-space-sm">
        <div className="min-w-0">
          <div
            className="truncate font-headline-sm text-headline-sm tabular-nums"
            style={{ color: favoreceA ? PALETA_POLOS.positivo : TOKENS.texto }}
          >
            {fator.valor_a ?? "—"}
          </div>
          <div className="truncate font-label-caps text-label-caps text-outline">{nomeA}</div>
        </div>
        <div className="min-w-0 text-right">
          <div
            className="truncate font-headline-sm text-headline-sm tabular-nums"
            style={{
              color:
                !favoreceA && fator.diferenca !== null ? PALETA_POLOS.negativo : TOKENS.texto,
            }}
          >
            {fator.valor_b ?? "—"}
          </div>
          <div className="truncate font-label-caps text-label-caps text-outline">{nomeB}</div>
        </div>
      </div>

      {indefinido ? (
        <div className="mt-space-sm font-body-sm text-body-sm text-outline">
          sem dado dos dois lados
        </div>
      ) : (
        <div className="mt-space-sm">
          <BarraSegmentada fracaoA={fracaoA} altura="h-1.5" />
        </div>
      )}
      {fator.unidade && (
        <div className="mt-space-xxs text-right font-label-caps text-label-caps text-outline">
          {fator.unidade}
        </div>
      )}
    </div>
  );
}

/**
 * O detalhe de um confronto: placar de probabilidade e os fatores por tras.
 *
 * Montado no modal do kanban e na secao de confronto hipotetico - por isso e um
 * componente, e nao um trecho inline.
 *
 * O desenho segue o mesmo HUD denso das outras telas ML do projeto (faixa de
 * motor + confianca, cartoes com brilho, barra de probabilidade grossa) —
 * mas so com o que existe ANTES da partida: forca, winrate, medias por time,
 * confrontos diretos. Nao ha placar de abates, torres ou curva de vantagem
 * minuto a minuto porque essa telemetria e de partida EM ANDAMENTO, e o
 * projeto removeu esse modelo (Fase 6) — usar os mesmos rotulos aqui venderia
 * um dado que a tela nao tem.
 */
function DetalheConfronto({
  previsao,
  jogo,
  priorExterno = null,
}: {
  previsao: TipoPrevisao;
  jogo: string;
  priorExterno?: PrioExternoConfronto | null;
}) {
  const favoritoA = previsao.probabilidade_a >= previsao.probabilidade_b;
  const corFavorito = favoritoA ? PALETA_POLOS.positivo : PALETA_POLOS.negativo;
  // Rearma sempre que o confronto muda (outro card do kanban, outra dupla no
  // simulador) - a barra volta a crescer do meio pra fora em vez de saltar.
  const entrou = useEntrarNaTela(`${previsao.equipe_a.id_equipe}-${previsao.equipe_b.id_equipe}`);

  return (
    <div className="space-y-space-lg">
      {/* ---------- Motor de previsao + confianca ---------- */}
      <div className="flex flex-wrap items-center justify-between gap-space-sm rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-space-lg py-space-sm">
        <span className="flex flex-wrap items-center gap-space-xs font-title-code text-title-code uppercase tracking-widest text-on-surface-variant">
          <Icone nome="psychology" className="text-[16px] text-primary" />
          Motor de previsão
          <span className="text-outline">· Bradley-Terry regularizado</span>
          {priorExterno && (
            <span
              className="text-outline"
              title={`Prior: diferença de ranking da ${priorExterno.fonte} (peso ${fmtDecimal(
                priorExterno.peso,
                2,
              )}, snapshot de ${priorExterno.data_mais_recente}). Puxa o time de pouco histórico para a posição dele no ranking em vez de para 50%.`}
            >
              · prior: ranking {priorExterno.fonte}
            </span>
          )}
        </span>
        <BadgeConfianca validacao={previsao.validacao} />
      </div>

      <div className="space-y-space-lg rounded-lg bg-surface-container-lowest p-space-lg">
        <div className="flex flex-col items-center gap-space-lg sm:flex-row">
          <LadoDoConfronto
            equipe={previsao.equipe_a}
            probabilidade={previsao.probabilidade_a}
            cor={PALETA_POLOS.positivo}
            rotuloLado={rotuloDoLado(jogo, "a")}
          />
          <span className="font-headline-md text-headline-md text-outline">VS</span>
          <LadoDoConfronto
            equipe={previsao.equipe_b}
            probabilidade={previsao.probabilidade_b}
            cor={PALETA_POLOS.negativo}
            rotuloLado={rotuloDoLado(jogo, "b")}
          />
        </div>

        {/* Barra de probabilidade em destaque - o "placar" desta tela. Cresce
            dos dois lados a partir do meio (50/50) ate o placar de verdade. */}
        <div
          className="flex h-3 w-full overflow-hidden rounded-full bg-surface-container-highest"
          style={{ boxShadow: `0 0 18px ${corFavorito}4d` }}
        >
          <div
            className="h-full"
            style={{
              width: `${(entrou ? previsao.probabilidade_a : 0.5) * 100}%`,
              background: `linear-gradient(90deg, ${PALETA_POLOS.positivo}99, ${PALETA_POLOS.positivo})`,
              transition: "width 800ms cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          />
          <div
            className="h-full flex-1"
            style={{
              background: `linear-gradient(90deg, ${PALETA_POLOS.negativo}, ${PALETA_POLOS.negativo}99)`,
              transition: "width 800ms cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          />
        </div>

        <BarraSegmentada
          fracaoA={previsao.probabilidade_a}
          legendaEsquerda={
            previsao.confrontos_diretos > 0 ? (
              <>
                Confrontos diretos: {previsao.vitorias_diretas_a}–
                {previsao.confrontos_diretos - previsao.vitorias_diretas_a} para{" "}
                {previsao.equipe_a.nome}
              </>
            ) : (
              <>Nunca se enfrentaram nos dados coletados</>
            )
          }
          legendaDireita={
            previsao.probabilidade_a >= 0.5
              ? previsao.equipe_a.nome.toUpperCase()
              : previsao.equipe_b.nome.toUpperCase()
          }
        />
      </div>

      {/* ---------- Estatisticas pre-partida ---------- */}
      <div>
        <h3 className="flex items-center gap-space-xs font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
          <Icone nome="balance" className="text-[20px] text-primary" />
          Estatísticas pré-partida
        </h3>
        <p className="mt-space-xxs font-body-sm text-body-sm text-outline">
          A força e as features de contexto marcadas entram na conta. As outras linhas
          descrevem os times, mas não são somadas — já estão embutidas na força.
        </p>

        <div className="mt-space-md grid grid-cols-1 gap-space-sm sm:grid-cols-2 lg:grid-cols-3">
          {previsao.fatores.map((fator) => (
            <CartaoFator
              key={fator.rotulo}
              fator={fator}
              nomeA={previsao.equipe_a.nome}
              nomeB={previsao.equipe_b.nome}
            />
          ))}
        </div>

        <p className="mt-space-md font-body-sm text-body-sm text-outline">
          <Icone nome="bolt" className="text-[14px] text-primary" /> marca o que o modelo
          pesou: a força (estimada de quem venceu quem) e, quando mostraram sinal, a forma
          recente, o confronto direto e o saldo de placar. Uma feature de contexto só
          entra com peso positivo — a direção dela é conhecida.
        </p>
      </div>

      {/* ---------- A conta: a log-odds decomposta ---------- */}
      <ContaLogOdds
        contribuicoes={previsao.contribuicoes}
        probabilidadeA={previsao.probabilidade_a}
        nomeA={previsao.equipe_a.nome}
        nomeB={previsao.equipe_b.nome}
      />
    </div>
  );
}

/** A soma que vira a probabilidade: cada parcela em log-odds, e a sigmoide no fim. */
function ContaLogOdds({
  contribuicoes,
  probabilidadeA,
  nomeA,
  nomeB,
}: {
  contribuicoes: ContribuicaoConfronto[];
  probabilidadeA: number;
  nomeA: string;
  nomeB: string;
}) {
  const total = contribuicoes.reduce((s, c) => s + c.log_odds, 0);
  const maior = Math.max(...contribuicoes.map((c) => Math.abs(c.log_odds)), 0.01);

  return (
    <div className="rounded-lg bg-surface-container p-space-base">
      <div className="flex items-center justify-between font-label-caps text-label-caps uppercase tracking-widest text-outline">
        <span>De onde saiu a probabilidade (log-odds)</span>
        <span>+ favorece {nomeA} · − favorece {nomeB}</span>
      </div>

      <div className="mt-space-md flex flex-col gap-space-xs">
        {contribuicoes.map((c) => {
          const positivo = c.log_odds >= 0;
          return (
            <div key={c.rotulo} className="flex items-center gap-space-sm">
              <span className="w-40 shrink-0 truncate font-body-sm text-body-sm text-on-surface-variant">
                {c.rotulo}
              </span>
              <div className="relative h-3 flex-1 rounded-full bg-surface-container-highest">
                <div
                  className="absolute top-0 h-3 rounded-full"
                  style={{
                    left: positivo ? "50%" : `${50 - (Math.abs(c.log_odds) / maior) * 50}%`,
                    width: `${(Math.abs(c.log_odds) / maior) * 50}%`,
                    background: positivo ? TOKENS.primaria : TOKENS.terciaria,
                  }}
                />
                <div className="absolute left-1/2 top-0 h-3 w-px bg-outline-variant" />
              </div>
              <span
                className="w-16 shrink-0 text-right font-title-code text-title-code tabular-nums"
                style={{ color: positivo ? TOKENS.primaria : TOKENS.terciaria }}
              >
                {positivo ? "+" : ""}
                {fmtDecimal(c.log_odds, 3)}
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-space-md flex items-center justify-between border-t border-outline-variant/30 pt-space-sm font-body-sm text-body-sm">
        <span className="text-on-surface-variant">
          Soma {fmtDecimal(total, 3)} → sigmoide →{" "}
          <span className="font-title-code text-title-code text-primary">
            {fmtPercentual(probabilidadeA * 100, 1)}
          </span>{" "}
          para {nomeA}
        </span>
      </div>
    </div>
  );
}

/** Um card do kanban. */
function CardConfronto({
  jogo,
  aoClicar,
}: {
  jogo: ConfrontoAgendado;
  aoClicar: () => void;
}) {
  const tem = jogo.probabilidade_a !== null;
  const favoritoA = (jogo.probabilidade_a ?? 0.5) >= 0.5;
  const horario = new Date(jogo.inicio_previsto).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });

  const lados = [
    { nome: jogo.equipe_a_nome, valor: jogo.probabilidade_a, cor: PALETA_POLOS.positivo },
    {
      nome: jogo.equipe_b_nome,
      valor: jogo.probabilidade_a === null ? null : 1 - jogo.probabilidade_a,
      cor: PALETA_POLOS.negativo,
    },
  ];

  return (
    <button
      type="button"
      onClick={aoClicar}
      className="w-full rounded-lg bg-surface-container-lowest p-space-md text-left shadow-sm transition-colors hover:bg-surface-container"
      style={{
        boxShadow: `inset 3px 0 0 ${
          tem
            ? favoritoA
              ? PALETA_POLOS.positivo
              : PALETA_POLOS.negativo
            : TOKENS.contornoSuave
        }`,
      }}
    >
      <div className="flex items-center justify-between gap-space-xs">
        <span className="font-title-code text-title-code text-primary">{horario}</span>
        {jogo.formato && (
          <span className="rounded bg-surface-container px-space-xs py-space-xxs font-badge-status text-badge-status text-outline">
            {jogo.formato}
          </span>
        )}
      </div>

      <div className="mt-space-sm space-y-space-xxs">
        {lados.map((lado) => (
          <div key={lado.nome} className="flex items-center justify-between gap-space-xs">
            <span
              className="min-w-0 flex-1 truncate font-headline-sm text-headline-sm"
              style={{
                color: lado.valor !== null && lado.valor >= 0.5 ? lado.cor : TOKENS.texto,
              }}
            >
              {lado.nome}
            </span>
            <span
              className="shrink-0 font-title-code text-title-code tabular-nums"
              style={{ color: lado.valor !== null ? lado.cor : TOKENS.contorno }}
            >
              {lado.valor === null ? "—" : fmtPercentual(lado.valor * 100, 0)}
            </span>
          </div>
        ))}
      </div>

      {tem ? (
        <div className="mt-space-sm">
          <BarraSegmentada fracaoA={jogo.probabilidade_a!} altura="h-1.5" />
        </div>
      ) : (
        <div
          className="mt-space-sm font-label-caps text-label-caps uppercase tracking-widest text-outline"
          title={jogo.motivo_sem_previsao ?? undefined}
        >
          {/* O rotulo era fixo em "sem historico coletado", e isso passou a
              mentir: num jogo sem modelo ajustado nao falta o historico DESTE
              time - falta o ajuste do jogo inteiro. */}
          {jogo.motivo_sem_previsao?.startsWith("o modelo")
            ? "sem modelo para este jogo"
            : "sem histórico coletado"}
        </div>
      )}

      {jogo.torneio && (
        <div className="mt-space-sm truncate font-body-sm text-body-sm text-outline">
          {jogo.torneio}
        </div>
      )}
    </button>
  );
}

/** Rótulo da coluna: "Hoje", "Amanhã" ou a data. */
function rotuloDoDia(dia: string): string {
  const data = new Date(`${dia}T12:00:00`);
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);

  const meiaNoite = new Date(data);
  meiaNoite.setHours(0, 0, 0, 0);

  const diferenca = Math.round((meiaNoite.getTime() - hoje.getTime()) / 86400_000);
  if (diferenca === 0) return "Hoje";
  if (diferenca === 1) return "Amanhã";

  return data.toLocaleDateString("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
  });
}

export function PrevisaoConfrontoPagina() {
  const [liga, setLiga] = useState<string | null>(null);
  const [minPartidas, setMinPartidas] = useState(3);
  const [equipeA, setEquipeA] = useState<number | null>(null);
  const [equipeB, setEquipeB] = useState<number | null>(null);
  const [soComPrevisao, setSoComPrevisao] = useState(false);
  const [aberto, setAberto] = useState<ConfrontoAgendado | null>(null);

  // A tela nao lia o chip do topo: trocar de jogo nao mudava nada aqui, e a
  // API respondia sempre sobre Dota 2, que e o padrao dela.
  const { jogo } = useJogoAtual();

  const relatorio = useRelatorioConfronto(jogo);
  const ligas = useLigasConfronto(jogo);
  const ranking = useRankingConfronto(jogo, liga, minPartidas);
  const agenda = useAgendaConfronto(jogo, soComPrevisao);
  const previsao = usePrevisaoConfronto(jogo, equipeA, equipeB);

  // Trocar de jogo limpa a selecao: um `id_equipe` de Dota nao existe em
  // Counter-Strike, e mante-lo pediria a previsao de um par que nao existe.
  useEffect(() => {
    setEquipeA(null);
    setEquipeB(null);
    setLiga(null);
    setAberto(null);
  }, [jogo]);

  const equipes = useMemo(() => ranking.data ?? [], [ranking.data]);

  // Assim que o ranking chega, escolhe o primeiro contra o ultimo: a secao de
  // confronto hipotetico abre com um par de verdade em vez de seletores vazios.
  //
  // `if (aberto) return`: sem essa guarda, este efeito criava um loop com
  // `abrir()`. O ranking e filtrado por `min_partidas` (padrao 3), e um card
  // do kanban pode envolver um time com menos partidas que isso - ele tem
  // previsao (o endpoint /agenda so exige `partidas > 0`), mas nao esta no
  // array `equipes` filtrado. `abrir()` selecionava o par certo, e no MESMO
  // ciclo este efeito via que ele "nao e valido" (nao esta em `equipes`) e
  // desfazia para o par padrao - o modal nunca via a previsao do confronto
  // que a pessoa clicou, so o esqueleto de carregamento, para sempre. Uma
  // selecao vinda de um clique no kanban e explicita e vence o default.
  useEffect(() => {
    if (aberto) return;
    if (equipes.length < 2) return;
    const validos = new Set(equipes.map((e) => e.id_equipe));
    if (equipeA === null || !validos.has(equipeA)) setEquipeA(equipes[0].id_equipe);
    if (equipeB === null || !validos.has(equipeB)) {
      setEquipeB(equipes[equipes.length - 1].id_equipe);
    }
  }, [equipes, equipeA, equipeB, aberto]);

  /** A agenda agrupada por dia - as colunas do kanban. */
  const colunas = useMemo(() => {
    const porDia = new Map<string, ConfrontoAgendado[]>();
    for (const jogo of agenda.data ?? []) {
      const dia = jogo.inicio_previsto.slice(0, 10);
      porDia.set(dia, [...(porDia.get(dia) ?? []), jogo]);
    }
    return [...porDia.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .slice(0, DIAS_NO_KANBAN);
  }, [agenda.data]);

  /**
   * Abre o modal de um card.
   *
   * A previsao vem do MESMO hook que a secao hipotetica usa, entao clicar num
   * card tambem move os seletores de baixo - o que e util: da para continuar
   * explorando a partir daquele confronto depois de fechar o modal.
   */
  function abrir(jogo: ConfrontoAgendado) {
    if (jogo.equipe_a && jogo.equipe_b) {
      setEquipeA(jogo.equipe_a.id_equipe);
      setEquipeB(jogo.equipe_b.id_equipe);
    }
    setAberto(jogo);
  }

  const semPrevisaoNoModal = Boolean(aberto && (!aberto.equipe_a || !aberto.equipe_b));

  // So mostra a previsao quando ela e DESTE confronto: o hook demora um render
  // para trocar, e sem esta checagem o modal exibiria por um instante os times
  // do card anterior.
  const previsaoDoModal =
    aberto &&
    !semPrevisaoNoModal &&
    previsao.data &&
    previsao.data.equipe_a.id_equipe === aberto.equipe_a?.id_equipe &&
    previsao.data.equipe_b.id_equipe === aberto.equipe_b?.id_equipe
      ? previsao.data
      : undefined;

  /**
   * O relatorio do ajuste - `undefined` quando este jogo nunca foi ajustado.
   *
   * Antes a tela inteira vivia dentro de um `<Consulta estado={relatorio}>`, e
   * o efeito era que um jogo sem modelo nao mostrava NADA - nem o calendario,
   * que vem de outra fonte e funciona. Agora a ausencia do modelo esconde so o
   * que depende dele: o ranking de forca, o confronto hipotetico e a lista de
   * campeonatos. A agenda continua na tela.
   */
  const dados: RelatorioConfronto | undefined = relatorio.data;

  if (relatorio.isPending) return <Esqueleto altura={320} />;

  return (
    <>
          {/* ==================== CABECALHO ==================== */}
          <section className="flex flex-col gap-space-base pt-space-base lg:flex-row lg:items-center lg:justify-between">
            <div className="flex flex-col gap-space-xs">
              <div className="flex flex-wrap items-center gap-space-sm">
                <h1 className="font-headline-lg text-headline-lg uppercase tracking-wide text-primary drop-shadow-[0_0_12px_rgba(0,229,255,0.4)]">
                  Previsão de Confronto
                </h1>
                <Selo cor="primario">Antes da partida</Selo>
                <span className="hidden font-label-caps text-label-caps uppercase tracking-wider text-outline sm:inline">
                  ML // Deck 05
                </span>
              </div>

              {dados ? (
                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  Qual time tem mais chance de vencer, a partir do histórico de{" "}
                  {fmtNumero(dados.confrontos)} confrontos entre {dados.equipes} equipes.
                  Método: <strong>{dados.metodo}</strong>.
                </p>
              ) : (
                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  O calendário deste jogo vem da Liquipedia e aparece abaixo.{" "}
                  <strong className="text-error">A previsão, não:</strong> ela precisa de
                  partidas com resultado — no Dota 2 vêm da OpenDota, nos outros jogos do
                  histórico da Liquipedia — e ainda não há o bastante para este jogo.
                </p>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-space-sm">
              {/* Criterio mais largo que o padrao do componente (so partidas):
                  a agenda de um jogo pode existir antes de qualquer confronto
                  DECIDIDO dele ter sido coletado - e ai ainda nao ha modelo. */}
              <SeletorDeJogo
                disponivel={(item) =>
                  item.partidas > 0 || item.equipes > 0 || item.agenda > 0
                }
              />

              <label className="flex items-center gap-space-xs">
                <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  Campeonato
                </span>
                <select
                  value={liga ?? ""}
                  onChange={(evento) => setLiga(evento.target.value || null)}
                  className={CAMPO}
                >
                  <option value="">Todos</option>
                  {ligas.data?.map((item: LigaConfronto) => (
                    <option key={item.liga} value={item.liga}>
                      {item.liga} ({item.confrontos})
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex items-center gap-space-xs">
                <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                  Mín. partidas
                </span>
                <select
                  value={minPartidas}
                  onChange={(evento) => setMinPartidas(Number(evento.target.value))}
                  className={CAMPO}
                >
                  {[1, 2, 3, 5].map((valor) => (
                    <option key={valor} value={valor}>
                      {valor}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>

          {dados && <AvisoValidacao validacao={dados.validacao} />}

          {/* ==================== KANBAN DA AGENDA ==================== */}
          <Painel
            icone="view_kanban"
            titulo="Próximos confrontos"
            // Era "Calendário da Liquipedia" fixo. Deixou de ser verdade
            // quando League of Legends passou a vir do OP.GG: a frase é uma
            // afirmação de procedência, e afirmar a fonte errada é o mesmo
            // defeito que marcar dado de terceiro como medição nossa.
            descricao={`Calendário ${
              jogo === "leagueoflegends" ? "do OP.GG" : "da Liquipedia"
            }, uma coluna por dia. Clique num card para ver as estatísticas e o porquê.`}
            meta={
              <Pilula
                ativa={soComPrevisao}
                icone="filter_alt"
                aoClicar={() => setSoComPrevisao((atual) => !atual)}
              >
                Só com previsão
              </Pilula>
            }
          >
            <Consulta
              estado={agenda}
              vazio="Nenhum confronto futuro na agenda. Colete com `cli.py collect liquipedia`."
            >
              {() =>
                colunas.length === 0 ? (
                  <p className="rounded bg-surface-container px-space-base py-space-md font-body-md text-body-md text-on-surface-variant">
                    Nenhum confronto futuro no recorte.
                  </p>
                ) : (
                  <div className="rolagem-discreta flex gap-space-base overflow-x-auto pb-space-sm">
                    {colunas.map(([dia, jogos]) => {
                      const comPrevisao = jogos.filter(
                        (jogo) => jogo.probabilidade_a !== null,
                      ).length;

                      return (
                        <div key={dia} className="flex w-72 shrink-0 flex-col gap-space-sm">
                          <div className="flex items-center justify-between gap-space-xs rounded bg-surface-container px-space-md py-space-sm">
                            <span className="font-title-code text-title-code uppercase tracking-wider text-on-surface">
                              {rotuloDoDia(dia)}
                            </span>
                            <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                              {jogos.length} jogo{jogos.length === 1 ? "" : "s"}
                              {comPrevisao > 0 && (
                                <span className="ml-space-xs text-primary">
                                  · {comPrevisao} c/ previsão
                                </span>
                              )}
                            </span>
                          </div>

                          <div className="flex flex-col gap-space-sm">
                            {jogos.map((jogo) => (
                              <CardConfronto
                                key={jogo.id_externo}
                                jogo={jogo}
                                aoClicar={() => abrir(jogo)}
                              />
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )
              }
            </Consulta>

            <p className="font-body-sm text-body-sm text-outline">
              Um confronto sem previsão é um em que pelo menos um dos times nunca apareceu
              num confronto decidido que coletamos — no Dota 2 o histórico vem da OpenDota,
              nos outros jogos do próprio ticker da Liquipedia.
            </p>
          </Painel>

          {/* ==================== MODAL DO CARD ==================== */}
          <Modal
            aberto={aberto !== null}
            aoFechar={() => setAberto(null)}
            titulo={aberto ? `${aberto.equipe_a_nome} vs ${aberto.equipe_b_nome}` : ""}
            descricao={
              aberto ? (
                <>
                  {fmtDataHora(aberto.inicio_previsto)}
                  {aberto.torneio && ` · ${aberto.torneio}`}
                  {aberto.formato && ` · ${aberto.formato}`}
                </>
              ) : undefined
            }
          >
            {semPrevisaoNoModal && aberto ? (
              <div className="space-y-space-base">
                <div
                  className="flex items-start gap-space-sm rounded-lg px-space-lg py-space-base"
                  style={{
                    border: `1px solid ${PALETA_POLOS.negativo}55`,
                    background: `${PALETA_POLOS.negativo}0d`,
                  }}
                >
                  <Icone nome="help" className="mt-[2px] text-[18px]" />
                  <div className="font-body-md text-body-md text-on-surface-variant">
                    <strong className="text-on-surface">
                      Sem previsão para este confronto.
                    </strong>{" "}
                    {aberto.motivo_sem_previsao}. O histórico vem da OpenDota no Dota 2 e
                    do ticker da Liquipedia nos outros jogos. Um time só recebe força
                    depois de aparecer num confronto decidido — coletar mais é o que
                    resolve.
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2">
                  {[
                    { nome: aberto.equipe_a_nome, equipe: aberto.equipe_a },
                    { nome: aberto.equipe_b_nome, equipe: aberto.equipe_b },
                  ].map((lado) => (
                    <div
                      key={lado.nome}
                      className="rounded-lg bg-surface-container-lowest p-space-base"
                    >
                      <div className="font-headline-sm text-headline-sm text-on-surface">
                        {lado.nome}
                      </div>
                      <div className="mt-space-xxs font-body-sm text-body-sm text-outline">
                        {lado.equipe
                          ? `${lado.equipe.vitorias}/${lado.equipe.partidas} partidas coletadas · força ${fmtDecimal(lado.equipe.forca, 3)}`
                          : "nenhuma partida coletada"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : previsao.isError ? (
              <MensagemErro erro={previsao.error} />
            ) : previsaoDoModal ? (
              <DetalheConfronto previsao={previsaoDoModal} jogo={jogo} priorExterno={dados?.prior_externo ?? null} />
            ) : (
              <div className="h-48 animate-pulse rounded bg-surface-container-high/60" />
            )}
          </Modal>

          {/* As tres secoes abaixo leem as FORCAS ajustadas. Sem modelo elas
              so teriam erros para mostrar, e tres paineis de erro empilhados
              dizem menos que uma frase no cabecalho. */}
          {dados && (
            <>
          {/* ==================== CONFRONTO HIPOTETICO ==================== */}
          <Painel
            icone="swords"
            titulo="Simular um confronto"
            descricao="Dois times quaisquer, com jogo agendado ou não. A vantagem de lado entra na conta separada da força."
            meta={
              equipes.length >= 2 ? (
                <button
                  type="button"
                  onClick={() => {
                    setEquipeA(equipeB);
                    setEquipeB(equipeA);
                  }}
                  className="inline-flex items-center gap-space-xs rounded bg-surface-container px-space-md py-space-xs font-title-code text-title-code text-primary transition-colors hover:bg-surface-container-high"
                >
                  <Icone nome="swap_horiz" className="text-[18px]" />
                  Inverter lados
                </button>
              ) : undefined
            }
          >
            <div className="flex flex-col gap-space-sm sm:flex-row">
              {(
                [
                  [rotuloDoLado(jogo, "a"), equipeA, setEquipeA],
                  [rotuloDoLado(jogo, "b"), equipeB, setEquipeB],
                ] as const
              ).map(([rotulo, valor, definir]) => (
                <label key={rotulo} className="flex flex-1 flex-col gap-space-xs">
                  <span className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
                    {rotulo}
                  </span>
                  <select
                    value={valor ?? ""}
                    onChange={(evento) => definir(Number(evento.target.value))}
                    className={`${CAMPO} w-full`}
                  >
                    {equipes.map((equipe) => (
                      <option key={equipe.id_equipe} value={equipe.id_equipe}>
                        {equipe.nome} ({equipe.vitorias}/{equipe.partidas})
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>

            {previsao.isError && <MensagemErro erro={previsao.error} />}

            <Consulta estado={previsao} altura={260} vazio="Escolha dois times diferentes.">
              {(resultado: TipoPrevisao) => (
                <DetalheConfronto previsao={resultado} jogo={jogo} priorExterno={dados?.prior_externo ?? null} />
              )}
            </Consulta>
          </Painel>

          {/* ==================== RANKING ==================== */}
          <Painel
            icone="leaderboard"
            titulo={liga ? `Ranking de força — ${liga}` : "Ranking de força"}
            descricao={
              dados?.prior_externo
                ? `Força é a estimativa do Bradley-Terry sobre os confrontos coletados, ancorada no ranking da ${dados.prior_externo.fonte} (coluna à parte). Não é a posição da ${dados.prior_externo.fonte}: um time com bom retrospecto sobe acima dela. Zero é a média; clique numa linha para colocá-la no lado A.`
                : "Força é a estimativa do Bradley-Terry sobre os confrontos coletados. Zero é a média; clique numa linha para colocá-la no lado A."
            }
            meta={
              <Selo cor="primario">
                {fmtNumero(equipes.length)} equipes com {minPartidas}+ partidas
              </Selo>
            }
          >
            <Consulta estado={ranking} vazio="Nenhuma equipe atinge esse mínimo.">
              {(lista: EquipeConfronto[]) => {
                const maiorForca = Math.max(...lista.map((e) => Math.abs(e.forca)), 0.01);
                // GPM/KDA são telemetria de MOBA (OpenDota → só Dota 2); a
                // posição da Valve só existe em CS. As colunas seguem o que o
                // jogo realmente tem, em vez de mostrar "—" numa tela de FPS.
                const temTelemetria = lista.some((e) => e.gpm_medio !== null);
                const temRankingExterno = lista.some(
                  (e) => e.posicao_ranking !== null,
                );
                // Saldo de mapas/jogos/pontos — existe onde a Liquipedia
                // publica o placar da série (todo jogo 1-contra-1 menos Dota).
                const temSaldo = lista.some((e) => e.saldo_placar !== null);

                return (
                  <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
                    <table className="w-full border-collapse text-left">
                      <thead>
                        <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
                          <th className="px-space-md py-space-sm">#</th>
                          <th className="px-space-md py-space-sm">Equipe</th>
                          <th className="px-space-md py-space-sm">Força</th>
                          <th className="px-space-md py-space-sm text-right">Partidas</th>
                          <th className="px-space-md py-space-sm text-right">Winrate</th>
                          {temSaldo && (
                            <th
                              className="px-space-md py-space-sm text-right"
                              title="Saldo médio de placar por confronto, de -1 (só perde de lavada) a +1 (só vence de lavada)"
                            >
                              Saldo
                            </th>
                          )}
                          {temRankingExterno && (
                            <th
                              className="px-space-md py-space-sm text-right"
                              title="Posição no Regional Standings da Valve"
                            >
                              Valve
                            </th>
                          )}
                          {temTelemetria && (
                            <>
                              <th className="px-space-md py-space-sm text-right">GPM</th>
                              <th className="px-space-md py-space-sm text-right">KDA</th>
                            </>
                          )}
                        </tr>
                      </thead>

                      <tbody className="font-body-md text-body-sm">
                        {lista.map((equipe, indice) => {
                          const positivo = equipe.forca >= 0;
                          const cor = positivo
                            ? PALETA_POLOS.positivo
                            : PALETA_POLOS.negativo;

                          return (
                            <tr
                              key={equipe.id_equipe}
                              onClick={() => setEquipeA(equipe.id_equipe)}
                              className={`cursor-pointer transition-colors hover:bg-surface-container-high/60 ${
                                indice % 2 ? "bg-[#131824]" : "bg-[#10141D]"
                              }`}
                              style={{
                                boxShadow:
                                  equipe.id_equipe === equipeA ||
                                  equipe.id_equipe === equipeB
                                    ? `inset 3px 0 0 ${TOKENS.primaria}`
                                    : undefined,
                              }}
                            >
                              <td className="px-space-md py-space-sm font-label-caps text-label-caps text-outline">
                                #{String(indice + 1).padStart(2, "0")}
                              </td>

                              <td className="px-space-md py-space-sm">
                                <span className="font-headline-sm text-headline-sm text-on-surface">
                                  {equipe.nome}
                                </span>
                                {equipe.tag && (
                                  <span className="ml-space-xs font-title-code text-title-code text-outline">
                                    {equipe.tag}
                                  </span>
                                )}
                              </td>

                              <td className="px-space-md py-space-sm">
                                <div className="flex items-center gap-space-sm">
                                  <BarraDivergente
                                    valor={equipe.forca}
                                    maximo={maiorForca}
                                    cor={cor}
                                  />
                                  <span
                                    className="font-title-code text-title-code tabular-nums"
                                    style={{ color: cor }}
                                  >
                                    {equipe.forca >= 0 ? "+" : ""}
                                    {fmtDecimal(equipe.forca, 3)}
                                  </span>
                                </div>
                              </td>

                              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                                {equipe.vitorias}/{equipe.partidas}
                              </td>
                              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface">
                                {fmtPercentual(equipe.winrate)}
                              </td>
                              {temSaldo && (
                                <td
                                  className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums"
                                  style={{
                                    color:
                                      equipe.saldo_placar === null
                                        ? undefined
                                        : equipe.saldo_placar >= 0
                                          ? PALETA_POLOS.positivo
                                          : PALETA_POLOS.negativo,
                                  }}
                                >
                                  {equipe.saldo_placar === null
                                    ? "—"
                                    : `${equipe.saldo_placar >= 0 ? "+" : ""}${fmtDecimal(
                                        equipe.saldo_placar,
                                        2,
                                      )}`}
                                </td>
                              )}
                              {temRankingExterno && (
                                <td
                                  className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant"
                                  title={
                                    equipe.pontos_ranking !== null
                                      ? `${equipe.pontos_ranking} pontos`
                                      : undefined
                                  }
                                >
                                  {equipe.posicao_ranking !== null
                                    ? `#${equipe.posicao_ranking}`
                                    : "—"}
                                </td>
                              )}
                              {temTelemetria && (
                                <>
                                  <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                                    {fmtNumero(equipe.gpm_medio)}
                                  </td>
                                  <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                                    {fmtDecimal(equipe.kda_medio, 2)}
                                  </td>
                                </>
                              )}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                );
              }}
            </Consulta>
          </Painel>

          {/* ==================== CAMPEONATOS ==================== */}
          <Painel
            icone="emoji_events"
            titulo="Campeonatos nos dados"
            descricao="A coleta pega partidas profissionais recentes; estes são os torneios que apareceram."
          >
            <Consulta estado={ligas} vazio="Nenhum campeonato coletado.">
              {(lista: LigaConfronto[]) => (
                <div className="grid grid-cols-1 gap-space-base md:grid-cols-2 xl:grid-cols-3">
                  {lista.map((item) => (
                    <button
                      key={item.liga}
                      type="button"
                      onClick={() => setLiga(liga === item.liga ? null : item.liga)}
                      className={`rounded-lg p-space-base text-left transition-colors ${
                        liga === item.liga
                          ? "bg-surface-container ring-1 ring-primary-container"
                          : "bg-surface-container-lowest hover:bg-surface-container"
                      }`}
                    >
                      <div className="font-headline-sm text-headline-sm text-on-surface">
                        {item.liga}
                      </div>
                      <div className="mt-space-xxs font-title-code text-title-code text-primary">
                        {item.confrontos} confrontos · {item.equipes} equipes
                      </div>
                      <div className="mt-space-xxs font-label-caps text-label-caps uppercase tracking-widest text-outline">
                        {fmtDataCurta(item.inicio)} — {fmtDataCurta(item.fim)}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </Consulta>
          </Painel>
            </>
          )}
    </>
  );
}
