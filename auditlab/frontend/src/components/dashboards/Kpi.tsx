/** Indicateur chiffré d'un tableau de bord. */
export default function Kpi({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="carte">
      <p className="text-sm text-slate-600">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
      {detail && <p className="text-xs text-slate-600">{detail}</p>}
    </div>
  );
}

/** Barre horizontale proportionnelle (sans bibliothèque de graphiques). */
export function Bar({
  label,
  value,
  max,
}: {
  label: string;
  value: number;
  max: number;
}) {
  const pct = max ? Math.round((value / max) * 100) : 0;
  return (
    <div className="grid grid-cols-[10rem_1fr_3rem] items-center gap-2 text-sm">
      <span>{label}</span>
      <span className="h-3 rounded bg-slate-100" aria-hidden="true">
        <span
          className="block h-3 rounded bg-marque-600"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="text-right">{value}</span>
    </div>
  );
}
