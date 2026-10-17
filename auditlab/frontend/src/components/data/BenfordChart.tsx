import { useTranslation } from "react-i18next";

import { formatNombre } from "../../lib/format";

export interface BenfordDigit {
  chiffres: number;
  observes: number;
  attendus: number;
  part_observee: number;
  part_attendue: number;
  z: number;
  significatif: boolean;
}

/** Proportions observées (barres) et attendues selon Benford (ligne), DAT-15. */
export default function BenfordChart({ digits }: { digits: BenfordDigit[] }) {
  const { t } = useTranslation();
  const W = 720;
  const H = 220;
  const pad = 30;
  const max = Math.max(...digits.map((d) => Math.max(d.part_observee, d.part_attendue))) * 1.1 || 1;
  const bw = (W - 2 * pad) / digits.length;
  const y = (v: number) => H - pad - (v / max) * (H - 2 * pad);
  const line = digits.map((d, i) => `${pad + bw * (i + 0.5)},${y(d.part_attendue)}`).join(" ");
  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={t("benford.graphique")}>
        <line x1={pad} x2={W - pad} y1={H - pad} y2={H - pad} stroke="#94a3b8" />
        {digits.map((d, i) => (
          <g key={d.chiffres}>
            <rect x={pad + bw * i + bw * 0.15} width={bw * 0.7} y={y(d.part_observee)} height={H - pad - y(d.part_observee)}
              fill={d.significatif ? "#dc2626" : "#3b82f6"}>
              <title>{`${d.chiffres} : ${formatNombre(Math.round(d.part_observee * 1000) / 10)} % / ${formatNombre(Math.round(d.part_attendue * 1000) / 10)} %`}</title>
            </rect>
            {(digits.length <= 10 || d.chiffres % 10 === 0) && (
              <text x={pad + bw * (i + 0.5)} y={H - pad + 14} fontSize="11" textAnchor="middle">{d.chiffres}</text>
            )}
          </g>
        ))}
        <polyline points={line} fill="none" stroke="#0f172a" strokeWidth="2" />
      </svg>
      <figcaption className="text-xs text-slate-600">{t("benford.legende")}</figcaption>
      <details className="text-sm">
        <summary className="cursor-pointer">{t("benford.tableau")}</summary>
        <table className="mt-1 w-full text-right text-xs">
          <thead>
            <tr>
              <th scope="col" className="text-left">{t("benford.chiffres")}</th>
              <th scope="col">{t("benford.observes")}</th>
              <th scope="col">{t("benford.attendus")}</th>
              <th scope="col">{t("benford.partObservee")}</th>
              <th scope="col">{t("benford.partAttendue")}</th>
              <th scope="col">z</th>
            </tr>
          </thead>
          <tbody>
            {digits.map((d) => (
              <tr key={d.chiffres} className={d.significatif ? "font-semibold text-red-700" : ""}>
                <td className="text-left">{d.chiffres}</td>
                <td>{formatNombre(d.observes)}</td>
                <td>{formatNombre(Math.round(d.attendus * 10) / 10)}</td>
                <td>{formatNombre(Math.round(d.part_observee * 10000) / 100)} %</td>
                <td>{formatNombre(Math.round(d.part_attendue * 10000) / 100)} %</td>
                <td>{formatNombre(Math.round(d.z * 100) / 100)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
