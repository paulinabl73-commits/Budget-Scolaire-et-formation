import { formatNombre } from "../../lib/format";

/** Diagramme en barres horizontales, sans dépendance (graphiques joints aux papiers). */
export default function BarChart({ points, label }: { points: { etiquette: string; valeur: number }[]; label: string }) {
  const max = Math.max(...points.map((p) => Math.abs(p.valeur)), 1);
  const row = 22;
  const W = 640;
  const left = 180;
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${points.length * row + 4}`} className="w-full" role="img" aria-label={label}>
        {points.map((p, i) => {
          const w = ((W - left - 90) * Math.abs(p.valeur)) / max;
          return (
            <g key={i} transform={`translate(0,${i * row})`}>
              <text x={left - 6} y="15" fontSize="11" textAnchor="end">{p.etiquette.length > 26 ? `${p.etiquette.slice(0, 25)}…` : p.etiquette}</text>
              <rect x={left} y="3" width={w} height={row - 6} fill={p.valeur < 0 ? "#dc2626" : "#3b82f6"} />
              <text x={left + w + 6} y="15" fontSize="11">{formatNombre(Math.round(p.valeur * 100) / 100)}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="text-xs text-slate-600">{label}</figcaption>
    </figure>
  );
}
