/**
 * Detalhe de um confronto de Valorant: o que aconteceu dentro da serie.
 *
 * A `ListaConfrontos` mostra o placar da serie (2x1). Aqui abrimos o grao de
 * baixo - um card por mapa com o placar e a duracao, e a linha de cada um dos
 * dez jogadores (agente, rating, ACS, K/D/A, ADR), do jeito que o vlr.gg
 * mostra. Vem de `agenda_partida.detalhe`, que so o coletor `vlr_detalhes`
 * preenche, entao so partida de Valorant ja decidida chega aqui.
 */

import { useConfrontoDetalhe } from "../api/consultas";
import type { JogadorNoMapa, MapaDoConfronto } from "../api/tipos";
import { Consulta, Icone } from "./base";
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
  // O detalhe grava `time` com o nome que o vlr.gg escreve na linha do
  // jogador; agrupamos por ele e, quando bate, damos a ordem A/B do confronto.
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
          : "Detalhe do confronto"
      }
      descricao={
        detalhe.data
          ? `Placar por mapa e stats por jogador · fonte ${detalhe.data.fonte}`
          : undefined
      }
      aoFechar={aoFechar}
    >
      <Consulta
        estado={detalhe}
        altura={240}
        vazio="Este confronto ainda não tem detalhe por mapa."
      >
        {(dados) => (
          <div className="space-y-space-base">
            {dados.mapas.map((mapa, i) => (
              <CardMapa
                key={`${mapa.nome ?? "mapa"}-${i}`}
                mapa={mapa}
                timeA={dados.equipe_a_nome}
                timeB={dados.equipe_b_nome}
              />
            ))}
          </div>
        )}
      </Consulta>
    </Modal>
  );
}
