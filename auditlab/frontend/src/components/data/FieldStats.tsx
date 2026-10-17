import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { post } from "../../api/client";
import type { Dataset } from "../../api/types";
import { formatDate, formatNombre } from "../../lib/format";
import Alert from "../Alert";

export interface GridQuery {
  filtres: Record<string, unknown>;
  recherche: string | null;
}

interface Stats {
  type: string;
  lignes: number;
  nombre: number;
  nulles: number;
  distinctes: number;
  min: unknown;
  max: unknown;
  total?: string;
  moyenne?: number | null;
  ecart_type?: number | null;
  positives?: number;
  negatives?: number;
  zeros?: number;
  frequentes: { valeur: unknown; nombre: number }[];
}

/** Statistiques de champ (DAT-08), sur la sélection affichée dans la grille. */
export default function FieldStats({ ds, column, query, onColumn }: {
  ds: Dataset;
  column: string;
  query: GridQuery;
  onColumn: (c: string) => void;
}) {
  const { t } = useTranslation();
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const type = ds.schema.find((c) => c.nom === column)?.type ?? "texte";

  useEffect(() => {
    setError(null);
    post<Stats>(`/datasets/${ds.id}/stats`, { colonne: column, ...query })
      .then(setStats)
      .catch((e: Error) => setError(e.message));
  }, [ds.id, column, query]);

  const show = (v: unknown) => {
    if (v === null || v === undefined) return "—";
    if (type === "decimal" || type === "entier") return formatNombre(Number(v));
    if (type === "date") return formatDate(String(v));
    return String(v);
  };
  const filtered = Object.keys(query.filtres).length > 0 || !!query.recherche;
  const rows: [string, string][] = stats
    ? [
        [t("stats.nombre"), formatNombre(stats.nombre)],
        [t("stats.nulles"), formatNombre(stats.nulles)],
        [t("stats.distinctes"), formatNombre(stats.distinctes)],
        ...(stats.total !== undefined
          ? ([
              [t("stats.total"), show(stats.total)],
              [t("stats.moyenne"), stats.moyenne == null ? "—" : formatNombre(Math.round(stats.moyenne * 100) / 100)],
              [t("stats.ecartType"), stats.ecart_type == null ? "—" : formatNombre(Math.round(stats.ecart_type * 100) / 100)],
            ] as [string, string][])
          : []),
        [t("stats.min"), show(stats.min)],
        [t("stats.max"), show(stats.max)],
        ...(stats.positives !== undefined
          ? ([
              [t("stats.positives"), formatNombre(stats.positives)],
              [t("stats.negatives"), formatNombre(stats.negatives ?? 0)],
              [t("stats.zeros"), formatNombre(stats.zeros ?? 0)],
            ] as [string, string][])
          : []),
      ]
    : [];

  return (
    <section className="carte space-y-2" aria-labelledby="stats-titre">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="stats-titre" className="text-base font-semibold">{t("stats.titre")}</h2>
        <div>
          <label htmlFor="stats-col" className="etiquette">{t("stats.champ")}</label>
          <select id="stats-col" className="champ mt-0" value={column} onChange={(e) => onColumn(e.target.value)}>
            {ds.schema.map((c) => <option key={c.nom} value={c.nom}>{c.nom}</option>)}
          </select>
        </div>
      </div>
      <p className="text-xs text-slate-600">
        {filtered ? t("stats.surSelection", { n: formatNombre(stats?.lignes ?? 0) }) : t("stats.surTable", { n: formatNombre(stats?.lignes ?? 0) })}
      </p>
      {error && <Alert kind="erreur">{error}</Alert>}
      {stats && (
        <div className="grid gap-4 md:grid-cols-2">
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
            {rows.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-slate-600">{k}</dt>
                <dd className="text-right font-mono">{v}</dd>
              </div>
            ))}
          </dl>
          <table className="text-sm">
            <caption className="text-left text-xs font-semibold text-slate-700">{t("stats.frequentes")}</caption>
            <thead className="sr-only">
              <tr><th scope="col">{t("stats.valeur")}</th><th scope="col">{t("stats.occurrences")}</th></tr>
            </thead>
            <tbody>
              {stats.frequentes.map((f, i) => (
                <tr key={i}>
                  <td className="truncate pr-2">{f.valeur === null ? <em>{t("stats.vide")}</em> : show(f.valeur)}</td>
                  <td className="text-right">{formatNombre(f.nombre)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
