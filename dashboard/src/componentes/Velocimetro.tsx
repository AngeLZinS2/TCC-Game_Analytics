/**
 * Velocímetro de probabilidade — o mostrador de 180° do modelo.
 *
 * A agulha e o arco preenchido em âmbar (`TOKENS.modelo`), a cor reservada ao
 * que o modelo *estima*; o número no centro, o rótulo (time favorito) abaixo.
 * O SVG pinta por atributo, então as cores vêm de `tema.ts` como string, não
 * de classe Tailwind.
 */

import { TOKENS } from "../tema";

export function Velocimetro({
  probabilidade,
  rotulo,
  tamanho = 240,
}: {
  /** Em [0, 1] — a fração para onde a agulha aponta. */
  probabilidade: number;
  /** Texto sob o número (ex.: nome do time favorito). */
  rotulo?: string;
  tamanho?: number;
}) {
  const p = Math.max(0, Math.min(1, probabilidade));

  const cx = 130;
  const cy = 130;
  const raioArco = 108;
  const raioAgulha = 74;
  // 180° (p=0, à esquerda) → 0° (p=1, à direita), medido do eixo x.
  const angulo = Math.PI * (1 - p);
  const fx = cx + raioArco * Math.cos(angulo);
  const fy = cy - raioArco * Math.sin(angulo);
  const nx = cx + raioAgulha * Math.cos(angulo);
  const ny = cy - raioAgulha * Math.sin(angulo);

  return (
    <svg
      viewBox="0 0 260 152"
      style={{ width: tamanho, maxWidth: "100%", height: "auto" }}
      role="img"
      aria-label={
        `Probabilidade do modelo: ${Math.round(p * 100)}%` +
        (rotulo ? ` para ${rotulo}` : "")
      }
    >
      <path
        d="M 22,130 A 108,108 0 0 1 238,130"
        fill="none"
        stroke={TOKENS.contornoSuave}
        strokeWidth="14"
        strokeLinecap="round"
      />
      <path
        d={`M 22,130 A 108,108 0 0 1 ${fx.toFixed(2)},${fy.toFixed(2)}`}
        fill="none"
        stroke={TOKENS.modelo}
        strokeWidth="14"
        strokeLinecap="round"
      />
      <line
        x1={cx}
        y1={cy}
        x2={nx.toFixed(2)}
        y2={ny.toFixed(2)}
        stroke={TOKENS.modelo}
        strokeWidth="3.5"
        strokeLinecap="round"
      />
      <circle cx={cx} cy={cy} r="4.5" fill={TOKENS.texto} />

      <text
        x="30"
        y="148"
        textAnchor="middle"
        fill={TOKENS.contorno}
        fontSize="11"
        fontFamily="Schibsted Grotesk, sans-serif"
      >
        0%
      </text>
      <text
        x="230"
        y="148"
        textAnchor="middle"
        fill={TOKENS.contorno}
        fontSize="11"
        fontFamily="Schibsted Grotesk, sans-serif"
      >
        100%
      </text>
      <text
        x="130"
        y="103"
        textAnchor="middle"
        fill={TOKENS.texto}
        fontSize="34"
        fontWeight="700"
        fontFamily="Schibsted Grotesk, sans-serif"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {Math.round(p * 100)}%
      </text>
      {rotulo && (
        <text
          x="130"
          y="122"
          textAnchor="middle"
          fill={TOKENS.textoSuave}
          fontSize="11"
          fontFamily="IBM Plex Sans, sans-serif"
          letterSpacing="0.04em"
        >
          {rotulo}
        </text>
      )}
    </svg>
  );
}
