/**
 * A tela de detalhe de uma partida — de qualquer estado, como a página de uma
 * partida no vlr.gg / hltv.org.
 *
 * Cabeçalho: status (EM BREVE / AO VIVO / ENCERRADA), os dois times com o
 * placar da série, o evento, o formato e o horário. Abaixo: onde assistir
 * (todos os canais), o resultado mapa a mapa, e — quando a fonte tem — a linha
 * de cada jogador por mapa: Valorant (agente/ACS/K-D-A, do vlr.gg) e LoL
 * (campeão/K-D-A/CS/ouro + objetivos, da API oficial da LoL Esports, ao vivo).
 *
 * Vem de `/api/partidas/confronto-detalhe`, que lê `agenda_partida` +
 * `agenda_partida.detalhe`. O plano free da PandaScore dá status + placar de
 * série + vencedor de cada mapa; stats por jogador só o scraping do vlr.gg / o
 * feed livestats da LoL Esports.
 */

import { useConfrontoDetalhe } from "@models/api/consultas";
import type {
  DetalheConfronto,
  JogadorNoMapa,
  MapaDoConfronto,
  ResultadoMapa,
  StatusPartida,
} from "@models/api/tipos";
import { corDoJogo, TOKENS } from "@views/tema";
import { fmtDataHora, fmtQuando } from "@util/formatos";
import { Consulta, Icone } from "./base";
import { CanaisTransmissao } from "./CanaisTransmissao";
import { Modal } from "./Modal";

/** Nome do agente com a inicial em maiuscula: `sova` -> `Sova`. */
function nomeAgente(agente: string | null): string {
  if (!agente) return "—";
  return agente.charAt(0).toUpperCase() + agente.slice(1);
}

/** Uma celula numerica; traço quando o parse nao pegou o valor. */
function Num({ valor, casas = 0 }: { valor: number | null; casas?: number }) {
  return (
    <td className="px-space-sm py-space-xs text-right font-title-code text-title-code tabular-nums text-on-surface">
      {valor === null ? "—" : valor.toFixed(casas)}
    </td>
  );
}

/* ------------------------------- Cabeçalho ------------------------------- */

const ROTULO_STATUS: Record<StatusPartida, string> = {
  em_breve: "Em breve",
  ao_vivo: "Ao vivo",
  encerrada: "Encerrada",
};

function SeloStatus({ status }: { status: StatusPartida }) {
  if (status === "ao_vivo") {
    return (
      <span className="inline-flex items-center gap-space-xxs rounded bg-error/15 px-space-xs py-space-xxs font-badge-status text-badge-status uppercase tracking-widest text-error">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-error" aria-hidden />
        ao vivo
      </span>
    );
  }
  const classe =
    status === "encerrada"
      ? "bg-surface-container text-on-surface-variant"
      : "bg-primary-container/20 text-primary";
  return (
    <span
      className={`inline-flex items-center rounded px-space-xs py-space-xxs font-badge-status text-badge-status uppercase tracking-widest ${classe}`}
    >
      {ROTULO_STATUS[status]}
    </span>
  );
}

function EscudoGrande({
  logo,
  tag,
  nome,
}: {
  logo: string | null;
  tag: string | null;
  nome: string;
}) {
  if (logo) {
    return (
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-neutral-200 p-[3px]">
        <img src={logo} alt="" className="max-h-full max-w-full object-contain" />
      </span>
    );
  }
  return (
    <span
      className="flex h-10 w-10 shrink-0 items-center justify-center rounded bg-surface-container-highest text-[11px] font-bold uppercase leading-none text-outline"
      aria-hidden
    >
      {(tag || nome).slice(0, 3)}
    </span>
  );
}

function LinhaTimeCabecalho({
  nome,
  logo,
  tag,
  placar,
  venceu,
  decidido,
  temPlacar,
}: {
  nome: string;
  logo: string | null;
  tag: string | null;
  placar: number | null;
  venceu: boolean;
  decidido: boolean;
  temPlacar: boolean;
}) {
  return (
    <div
      className="flex items-center gap-space-sm rounded-lg px-space-sm py-space-xs"
      style={{
        background: venceu ? `${TOKENS.terciaria}14` : undefined,
        boxShadow: venceu ? `inset 3px 0 0 ${TOKENS.terciaria}` : undefined,
      }}
    >
      <EscudoGrande logo={logo} tag={tag} nome={nome} />
      <span
        className={`min-w-0 flex-1 truncate font-title-code text-headline-sm ${
          decidido && !venceu ? "text-outline" : "text-on-surface"
        }`}
        title={nome}
      >
        {nome}
      </span>
      {temPlacar && (
        <span
          className="shrink-0 font-headline-md text-headline-md tabular-nums"
          style={{
            color: venceu
              ? TOKENS.terciaria
              : decidido
                ? TOKENS.erro
                : TOKENS.texto,
          }}
        >
          {placar ?? "–"}
        </span>
      )}
    </div>
  );
}

function Cabecalho({ d }: { d: DetalheConfronto }) {
  const temPlacar = d.placar_a != null || d.placar_b != null;
  const decidido = d.vitoria_a != null;
  const quando =
    d.status === "ao_vivo"
      ? "ao vivo agora"
      : d.inicio_previsto
        ? fmtQuando(d.inicio_previsto)
        : null;

  return (
    <div className="space-y-space-sm">
      <div className="flex flex-wrap items-center gap-space-sm">
        <SeloStatus status={d.status} />
        {d.jogo && (
          <span className="flex items-center gap-space-xxs font-label-caps text-label-caps uppercase tracking-wider text-outline">
            <span
              className="h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ background: corDoJogo(d.jogo) }}
              aria-hidden
            />
            {d.jogo_nome ?? d.jogo}
          </span>
        )}
        {d.torneio && (
          <span className="min-w-0 truncate font-body-sm text-body-sm text-on-surface-variant">
            <Icone nome="emoji_events" className="mr-space-xxs text-[13px]" />
            {d.torneio}
          </span>
        )}
      </div>

      <div className="space-y-space-xxs rounded-xl bg-surface-container-lowest p-space-xs">
        <LinhaTimeCabecalho
          nome={d.equipe_a_nome}
          logo={d.equipe_a_logo}
          tag={d.equipe_a_tag}
          placar={d.placar_a}
          venceu={d.vitoria_a === true}
          decidido={decidido}
          temPlacar={temPlacar}
        />
        <LinhaTimeCabecalho
          nome={d.equipe_b_nome}
          logo={d.equipe_b_logo}
          tag={d.equipe_b_tag}
          placar={d.placar_b}
          venceu={d.vitoria_a === false}
          decidido={decidido}
          temPlacar={temPlacar}
        />
      </div>

      <div className="flex flex-wrap items-center gap-space-sm font-badge-status text-badge-status uppercase tracking-wider text-outline">
        {d.formato && (
          <span className="rounded bg-surface-container px-space-xxs py-[1px] text-on-surface-variant">
            {d.formato}
          </span>
        )}
        {quando && (
          <span
            className="tabular-nums"
            title={d.inicio_previsto ? fmtDataHora(d.inicio_previsto) : undefined}
          >
            {quando}
          </span>
        )}
        <span className="text-outline/70">fonte {d.fonte}</span>
      </div>

      {d.veto && (
        <p className="rounded-lg bg-surface-container-lowest px-space-sm py-space-xs font-body-sm text-body-sm text-on-surface-variant">
          <Icone nome="rule" className="mr-space-xxs text-[13px] text-outline" />
          {d.veto}
        </p>
      )}
    </div>
  );
}

/* ---------------------------- Resultado por mapa ---------------------------- */

function TrilhaMapas({ mapas }: { mapas: ResultadoMapa[] }) {
  return (
    <section className="space-y-space-xs">
      <h3 className="font-label-caps text-label-caps uppercase tracking-wider text-outline">
        Mapas
      </h3>
      <div className="flex flex-wrap gap-space-xs">
        {mapas.map((m, i) => {
          const aoVivo = m.status === "ao_vivo";
          const decidido = m.vitoria_a != null;
          const rotulo = m.nome ?? `Mapa ${m.posicao ?? i + 1}`;
          return (
            <div
              key={`${rotulo}-${i}`}
              className="flex items-center gap-space-xs rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-space-sm py-space-xs"
              style={aoVivo ? { borderColor: `${TOKENS.erro}66` } : undefined}
            >
              <span className="font-title-code text-title-code text-on-surface-variant">
                {rotulo}
              </span>
              {m.placar_a != null && m.placar_b != null && (
                <span className="font-title-code text-title-code tabular-nums text-on-surface">
                  {m.placar_a}–{m.placar_b}
                </span>
              )}
              {aoVivo ? (
                <span className="flex items-center gap-space-xxs font-badge-status text-badge-status uppercase tracking-wider text-error">
                  <span
                    className="h-1.5 w-1.5 animate-pulse rounded-full bg-error"
                    aria-hidden
                  />
                  ao vivo
                </span>
              ) : decidido ? (
                <span
                  className="font-badge-status text-badge-status uppercase tracking-wider"
                  style={{ color: TOKENS.terciaria }}
                >
                  {m.vitoria_a ? "✓ A" : "✓ B"}
                </span>
              ) : m.status === "nao_jogado" ? (
                <span className="font-badge-status text-badge-status uppercase tracking-wider text-outline/60">
                  não jogado
                </span>
              ) : (
                <span className="font-badge-status text-badge-status uppercase tracking-wider text-outline">
                  a jogar
                </span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/* ---------------------- Scoreboard por jogador (Valorant) ---------------------- */

/** A tabela de um time dentro de um mapa, ordenada por ACS. */
function TabelaTime({
  time,
  jogadores,
}: {
  time: string;
  jogadores: JogadorNoMapa[];
}) {
  const linhas = [...jogadores].sort((a, b) => (b.acs ?? 0) - (a.acs ?? 0));

  return (
    <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
            <th className="px-space-sm py-space-xs">{time || "Time"}</th>
            <th className="px-space-sm py-space-xs text-right">Rating</th>
            <th className="px-space-sm py-space-xs text-right">ACS</th>
            <th className="px-space-sm py-space-xs text-right">K</th>
            <th className="px-space-sm py-space-xs text-right">D</th>
            <th className="px-space-sm py-space-xs text-right">A</th>
            <th className="px-space-sm py-space-xs text-right">ADR</th>
          </tr>
        </thead>
        <tbody className="font-body-md text-body-sm">
          {linhas.map((j, i) => (
            <tr key={`${j.nome}-${i}`} className={i % 2 ? "bg-[#131824]" : "bg-[#10141D]"}>
              <td className="px-space-sm py-space-xs">
                <div className="flex items-center gap-space-xs">
                  <span className="font-title-code text-title-code text-on-surface">
                    {j.nome}
                  </span>
                  <span className="rounded bg-surface-container px-space-xxs font-badge-status text-badge-status uppercase text-secondary">
                    {nomeAgente(j.agente)}
                  </span>
                </div>
              </td>
              <Num valor={j.rating} casas={2} />
              <Num valor={j.acs} />
              <Num valor={j.k} />
              <Num valor={j.d} />
              <Num valor={j.a} />
              <Num valor={j.adr} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------------- Scoreboard por jogador (LoL) ---------------------- */

function LinhaKda({ j }: { j: JogadorNoMapa }) {
  return (
    <span className="font-title-code text-title-code tabular-nums text-on-surface">
      {j.k ?? "—"}<span className="text-outline"> / </span>
      {j.d ?? "—"}<span className="text-outline"> / </span>
      {j.a ?? "—"}
    </span>
  );
}

function TabelaTimeLol({
  time,
  jogadores,
}: {
  time: string;
  jogadores: JogadorNoMapa[];
}) {
  return (
    <div className="rolagem-discreta overflow-x-auto rounded-lg bg-surface-container-lowest">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="bg-surface-container font-label-caps text-label-caps uppercase tracking-wider text-outline">
            <th className="px-space-sm py-space-xs">{time || "Time"}</th>
            <th className="px-space-sm py-space-xs text-right">K / D / A</th>
            <th className="px-space-sm py-space-xs text-right">CS</th>
            <th className="px-space-sm py-space-xs text-right">Ouro</th>
          </tr>
        </thead>
        <tbody className="font-body-md text-body-sm">
          {jogadores.map((j, i) => (
            <tr key={`${j.nome}-${i}`} className={i % 2 ? "bg-[#131824]" : "bg-[#10141D]"}>
              <td className="px-space-sm py-space-xs">
                <div className="flex items-center gap-space-xs">
                  <span className="font-title-code text-title-code text-on-surface">
                    {j.nome}
                  </span>
                  {j.campeao && (
                    <span className="rounded bg-surface-container px-space-xxs font-badge-status text-badge-status uppercase text-secondary">
                      {j.campeao}
                    </span>
                  )}
                </div>
              </td>
              <td className="px-space-sm py-space-xs text-right">
                <LinhaKda j={j} />
              </td>
              <Num valor={j.cs} />
              <td className="px-space-sm py-space-xs text-right font-title-code text-title-code tabular-nums text-on-surface">
                {j.ouro == null ? "—" : `${(j.ouro / 1000).toFixed(1)}k`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Objetivos({ o }: { o: NonNullable<MapaDoConfronto["objetivos_a"]> }) {
  const itens: [string, number | null][] = [
    ["Torres", o.torres],
    ["Dragões", o.dragoes],
    ["Barões", o.baroes],
  ];
  return (
    <span className="flex flex-wrap items-center gap-x-space-sm gap-y-space-xxs font-badge-status text-badge-status uppercase tracking-wider text-outline">
      {itens.map(([rotulo, v]) => (
        <span key={rotulo} className="tabular-nums">
          {rotulo} <span className="text-on-surface">{v ?? 0}</span>
        </span>
      ))}
      {o.ouro != null && (
        <span className="tabular-nums">
          Ouro <span className="text-on-surface">{(o.ouro / 1000).toFixed(1)}k</span>
        </span>
      )}
    </span>
  );
}

function CardMapaLol({
  mapa,
  timeA,
  timeB,
}: {
  mapa: MapaDoConfronto;
  timeA: string;
  timeB: string;
}) {
  const jogA = mapa.jogadores.filter((j) => j.time !== timeB);
  const jogB = mapa.jogadores.filter((j) => j.time === timeB);
  const venceuA =
    mapa.placar_a != null && mapa.placar_b != null && mapa.placar_a > mapa.placar_b;
  const venceuB =
    mapa.placar_a != null && mapa.placar_b != null && mapa.placar_b > mapa.placar_a;

  return (
    <div className="space-y-space-sm rounded-xl bg-surface-container-low p-space-base">
      <div className="flex flex-wrap items-baseline justify-between gap-space-sm border-b border-outline-variant/30 pb-space-xs">
        <h3 className="font-headline-sm text-headline-sm uppercase tracking-wide text-primary">
          {mapa.nome ?? "Jogo"}
        </h3>
        <div className="flex items-baseline gap-space-xs font-headline-sm text-headline-sm tabular-nums">
          <span className={venceuA ? "text-tertiary" : "text-outline"}>
            {mapa.placar_a ?? "-"}
          </span>
          <span className="text-outline">:</span>
          <span className={venceuB ? "text-tertiary" : "text-outline"}>
            {mapa.placar_b ?? "-"}
          </span>
        </div>
      </div>

      <div className="grid gap-space-sm lg:grid-cols-2">
        <div className="space-y-space-xxs">
          {mapa.objetivos_a && <Objetivos o={mapa.objetivos_a} />}
          <TabelaTimeLol time={timeA} jogadores={jogA} />
        </div>
        <div className="space-y-space-xxs">
          {mapa.objetivos_b && <Objetivos o={mapa.objetivos_b} />}
          <TabelaTimeLol time={timeB} jogadores={jogB} />
        </div>
      </div>
    </div>
  );
}

/** Um mapa: cabecalho com placar e duracao, e as duas tabelas de time. */
function CardMapa({
  mapa,
  timeA,
  timeB,
}: {
  mapa: MapaDoConfronto;
  timeA: string;
  timeB: string;
}) {
  const times = [...new Set(mapa.jogadores.map((j) => j.time))];
  const ordenados = times.sort((a, b) => {
    const rank = (t: string) => (t === timeA ? 0 : t === timeB ? 1 : 2);
    return rank(a) - rank(b);
  });

  const venceuA =
    mapa.placar_a !== null && mapa.placar_b !== null && mapa.placar_a > mapa.placar_b;
  const venceuB =
    mapa.placar_a !== null && mapa.placar_b !== null && mapa.placar_b > mapa.placar_a;

  return (
    <div className="space-y-space-sm rounded-xl bg-surface-container-low p-space-base">
      <div className="flex flex-wrap items-baseline justify-between gap-space-sm border-b border-outline-variant/30 pb-space-xs">
        <h3 className="font-headline-sm text-headline-sm uppercase tracking-wide text-primary">
          {mapa.nome ?? "Mapa"}
        </h3>
        <div className="flex items-baseline gap-space-xs font-headline-sm text-headline-sm tabular-nums">
          <span className={venceuA ? "text-tertiary" : "text-outline"}>
            {mapa.placar_a ?? "-"}
          </span>
          <span className="text-outline">:</span>
          <span className={venceuB ? "text-tertiary" : "text-outline"}>
            {mapa.placar_b ?? "-"}
          </span>
        </div>
        {mapa.duracao && (
          <span className="font-badge-status text-badge-status uppercase tracking-wider text-outline">
            <Icone nome="schedule" className="mr-space-xxs text-[14px]" />
            {mapa.duracao}
          </span>
        )}
      </div>

      <div className="grid gap-space-sm lg:grid-cols-2">
        {ordenados.map((time) => (
          <TabelaTime
            key={time}
            time={time}
            jogadores={mapa.jogadores.filter((j) => j.time === time)}
          />
        ))}
      </div>
    </div>
  );
}

/* --------------------------------- Modal --------------------------------- */

export function ModalConfrontoDetalhe({
  idExterno,
  aoFechar,
}: {
  idExterno: string | null;
  aoFechar: () => void;
}) {
  const detalhe = useConfrontoDetalhe(idExterno);

  return (
    <Modal
      aberto={idExterno !== null}
      titulo={
        detalhe.data
          ? `${detalhe.data.equipe_a_nome} vs ${detalhe.data.equipe_b_nome}`
          : "Detalhe da partida"
      }
      aoFechar={aoFechar}
    >
      <Consulta estado={detalhe} altura={240} vazio="Partida não encontrada.">
        {(d) => {
          const temScoreboard = d.mapas.some((m) => m.jogadores.length > 0);
          const semNada =
            !temScoreboard &&
            d.mapas_resultado.length === 0 &&
            d.streams.length === 0 &&
            !d.veto;

          return (
            <div className="space-y-space-base">
              <Cabecalho d={d} />

              {d.streams.length > 0 && (
                <section className="space-y-space-xs">
                  <h3 className="font-label-caps text-label-caps uppercase tracking-wider text-outline">
                    Onde assistir
                  </h3>
                  <CanaisTransmissao streams={d.streams} />
                </section>
              )}

              {d.mapas_resultado.length > 0 && (
                <TrilhaMapas mapas={d.mapas_resultado} />
              )}

              {temScoreboard && (
                <div className="space-y-space-base">
                  {d.mapas
                    .filter((m) => m.jogadores.length > 0)
                    .map((mapa, i) =>
                      d.jogo === "leagueoflegends" ? (
                        <CardMapaLol
                          key={`${mapa.nome ?? "jogo"}-${i}`}
                          mapa={mapa}
                          timeA={d.equipe_a_nome}
                          timeB={d.equipe_b_nome}
                        />
                      ) : (
                        <CardMapa
                          key={`${mapa.nome ?? "mapa"}-${i}`}
                          mapa={mapa}
                          timeA={d.equipe_a_nome}
                          timeB={d.equipe_b_nome}
                        />
                      ),
                    )}
                </div>
              )}

              {semNada && (
                <p className="rounded-lg bg-surface-container-lowest px-space-base py-space-md font-body-sm text-body-sm text-on-surface-variant">
                  {d.status === "em_breve"
                    ? "A partida ainda não começou. Volta aqui para acompanhar o placar e os canais de transmissão."
                    : "Sem placar por mapa desta partida — a fonte publica só o resultado da série."}
                </p>
              )}
            </div>
          );
        }}
      </Consulta>
    </Modal>
  );
}
