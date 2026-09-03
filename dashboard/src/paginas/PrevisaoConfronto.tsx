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

import {
  useAgendaConfronto,
  useLigasConfronto,
  usePrevisaoConfronto,
  useRankingConfronto,
  useRelatorioConfronto,
} from "../api/consultas";
import type {
  ConfrontoAgendado,
  EquipeConfronto,
  LigaConfronto,
  PrevisaoConfronto as TipoPrevisao,
  RelatorioConfronto,
  ValidacaoConfronto,
} from "../api/tipos";
import { Consulta, Esqueleto, Icone, MensagemErro, Selo } from "../componentes/base";
import { BarraSegmentada, CAMPO, Painel, Pilula } from "../componentes/hud";
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
 * O detalhe de um confronto: placar de probabilidade e os fatores por tras.
 *
 * Montado no modal do kanban e na secao de confronto hipotetico - por isso e um
 * componente, e nao um trecho inline.
 */
function DetalheConfronto({
  previsao,
  jogo,
}: {
  previsao: TipoPrevisao;
  jogo: string;
}) {
  return (
    <div className="space-y-space-lg">
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

      {/* ---------- Por que ---------- */}
      <div>
        <h3 className="flex items-center gap-space-xs font-headline-sm text-headline-sm uppercase tracking-wide text-on-surface">
          <Icone nome="balance" className="text-[20px] text-primary" />
          Por que essa chance
        </h3>
        <p className="mt-space-xxs font-body-sm text-body-sm text-outline">
          Só a força entra na conta da probabilidade. O resto é o contexto que explica de
          onde ela veio.
        </p>

        <div className="mt-space-md space-y-space-sm">
          {previsao.fatores.map((fator) => {
            /*
             * Barra proporcional, nao gradiente fixo: a largura de cada lado e
             * a fatia dele no total, entao a diferenca entre "588 x 452" e
             * "9,69 x 2,13" aparece na hora. Os valores sao deslocados para
             * nao-negativo antes da divisao porque a forca vai a numeros
             * negativos, e uma fracao com denominador que muda de sinal nao
             * significa nada.
             */
            const a = fator.valor_a ?? 0;
            const b = fator.valor_b ?? 0;
            const piso = Math.min(0, a, b);
            const total = a - piso + (b - piso);
            const fracaoA = total > 0 ? (a - piso) / total : 0.5;

            const indefinido = fator.valor_a === null || fator.valor_b === null;
            const favoreceA = (fator.diferenca ?? 0) > 0;

            return (
              <div
                key={fator.rotulo}
                className="flex items-center gap-space-sm rounded bg-surface-container px-space-md py-space-sm"
              >
                <span
                  className="w-24 shrink-0 text-right font-title-code text-title-code tabular-nums"
                  style={{ color: favoreceA ? PALETA_POLOS.positivo : TOKENS.textoSuave }}
                >
                  {fator.valor_a ?? "—"}
                </span>

                <div className="flex flex-1 flex-col items-center gap-space-xxs">
                  <span className="flex items-center gap-space-xs font-label-caps text-label-caps uppercase tracking-widest text-outline">
                    {fator.peso_no_modelo && (
                      <Icone nome="functions" className="text-[14px] text-primary" />
                    )}
                    {fator.rotulo}
                    {fator.unidade && ` (${fator.unidade})`}
                  </span>

                  {indefinido ? (
                    <span className="font-body-sm text-body-sm text-outline">
                      sem dado dos dois lados
                    </span>
                  ) : (
                    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-surface-container-highest">
                      <div
                        className="h-full"
                        style={{
                          width: `${fracaoA * 100}%`,
                          background: PALETA_POLOS.positivo,
                        }}
                      />
                      <div
                        className="h-full flex-1"
                        style={{ background: PALETA_POLOS.negativo }}
                      />
                    </div>
                  )}
                </div>

                <span
                  className="w-24 shrink-0 font-title-code text-title-code tabular-nums"
                  style={{
                    color:
                      !favoreceA && fator.diferenca !== null
                        ? PALETA_POLOS.negativo
                        : TOKENS.textoSuave,
                  }}
                >
                  {fator.valor_b ?? "—"}
                </span>
              </div>
            );
          })}
        </div>

        <p className="mt-space-md font-body-sm text-body-sm text-outline">
          <Icone nome="functions" className="text-[14px] text-primary" /> marca o único
          fator que entra na conta. Winrate, GPM e KDA descrevem os times, mas não são
          somados à probabilidade — eles já estão embutidos na força, que foi estimada a
          partir de quem venceu quem.
        </p>
      </div>

      {/* ---------- A conta ---------- */}
      <div className="grid grid-cols-1 gap-space-base sm:grid-cols-2">
        {(
          [
            [
              "Diferença de força (log-odds)",
              previsao.contribuicao_forca,
              3,
              "Positivo favorece o lado A",
              TOKENS.primaria,
            ],
            [
              "Vantagem de lado (log-odds)",
              previsao.contribuicao_lado,
              4,
              "O modelo separa isso da qualidade do time",
              TOKENS.secundaria,
            ],
          ] as const
        ).map(([rotulo, valor, casas, nota, cor]) => (
          <div key={rotulo} className="rounded-lg bg-surface-container p-space-base">
            <div className="font-label-caps text-label-caps uppercase tracking-widest text-outline">
              {rotulo}
            </div>
            <div
              className="mt-space-xxs font-headline-kpi text-headline-kpi leading-none"
              style={{ color: cor }}
            >
              {valor >= 0 ? "+" : ""}
              {fmtDecimal(valor, casas)}
            </div>
            <div className="mt-space-xxs font-body-sm text-body-sm text-outline">
              {nota}
            </div>
          </div>
        ))}
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
        <div className="mt-space-sm flex h-1.5 w-full overflow-hidden rounded-full bg-surface-container-highest">
          <div
            className="h-full"
            style={{
              width: `${jogo.probabilidade_a! * 100}%`,
              background: PALETA_POLOS.positivo,
            }}
          />
          <div className="h-full flex-1" style={{ background: PALETA_POLOS.negativo }} />
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
                  partidas com resultado, e a coleta de resultados vem da OpenDota, que
                  hoje só cobre Dota 2.
                </p>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-space-sm">
              {/* Criterio mais largo que o padrao do componente (so partidas):
                  a agenda existe sem nenhuma partida coletada, porque a coleta
                  de RESULTADO e so da OpenDota e so cobre Dota 2 hoje. */}
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
            descricao="Calendário da Liquipedia, uma coluna por dia. Clique num card para ver as estatísticas e o porquê."
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
              nas partidas coletadas — a agenda vem da Liquipedia e o histórico vem da
              OpenDota, e as duas cobrem torneios diferentes.
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
                    {aberto.motivo_sem_previsao}. A agenda vem da Liquipedia; o histórico,
                    da OpenDota. Um time só recebe força depois de aparecer em partidas
                    coletadas — coletar mais partidas é o que resolve.
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
              <DetalheConfronto previsao={previsaoDoModal} jogo={jogo} />
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
                <DetalheConfronto previsao={resultado} jogo={jogo} />
              )}
            </Consulta>
          </Painel>

          {/* ==================== RANKING ==================== */}
          <Painel
            icone="leaderboard"
            titulo={liga ? `Ranking de força — ${liga}` : "Ranking de força"}
            descricao="Zero é a média do conjunto. Clique numa linha para colocá-la no lado A."
            meta={
              <Selo cor="primario">
                {fmtNumero(equipes.length)} equipes com {minPartidas}+ partidas
              </Selo>
            }
          >
            <Consulta estado={ranking} vazio="Nenhuma equipe atinge esse mínimo.">
              {(lista: EquipeConfronto[]) => {
                const maiorForca = Math.max(...lista.map((e) => Math.abs(e.forca)), 0.01);

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
                          <th className="px-space-md py-space-sm text-right">GPM</th>
                          <th className="px-space-md py-space-sm text-right">KDA</th>
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
                                  <div className="relative h-1.5 w-24 rounded-full bg-surface-container-highest">
                                    <div
                                      className="absolute top-0 h-full rounded-full"
                                      style={{
                                        left: positivo ? "50%" : undefined,
                                        right: positivo ? undefined : "50%",
                                        width: `${(Math.abs(equipe.forca) / maiorForca) * 50}%`,
                                        background: cor,
                                      }}
                                    />
                                    <div
                                      className="absolute left-1/2 top-0 h-full w-[1px] bg-outline/60"
                                      aria-hidden
                                    />
                                  </div>
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
                              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                                {fmtNumero(equipe.gpm_medio)}
                              </td>
                              <td className="px-space-md py-space-sm text-right font-title-code text-title-code tabular-nums text-on-surface-variant">
                                {fmtDecimal(equipe.kda_medio, 2)}
                              </td>
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
