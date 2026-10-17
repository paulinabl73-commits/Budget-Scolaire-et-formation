import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";

interface Ratios {
  exercices: { periode: string; exercice: number; disponible: boolean }[];
  ratios: { code: string; libelle: string; famille: string | null; unite: string; valeurs: Record<string, string | null> }[];
}

/** Ratios financiers comparés sur trois exercices (REV-13). */
export default function RatiosPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Ratios | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Ratios>(`/audit-files/${file.id}/ratios`).then(setData).catch((e: Error) => setError(e.message));
  }, [file.id]);
  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!data) return null;
  const families = [...new Set(data.ratios.map((r) => r.famille ?? "autres"))];
  const unit = (u: string) => (u === "pourcentage" ? " %" : u === "jours" ? ` ${t("ratios.jours")}` : "");
  return (
    <section className="carte space-y-3" aria-labelledby="ratios-titre">
      <h2 id="ratios-titre" className="text-base font-semibold">{t("ratios.titre")}</h2>
      {data.exercices.some((e) => !e.disponible) && (
        <p className="text-sm text-slate-600">{t("ratios.indisponible", { exercices: data.exercices.filter((e) => !e.disponible).map((e) => e.exercice).join(", ") })}</p>
      )}
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-600">
          <tr>
            <th scope="col" className="py-1 pr-3">{t("ratios.ratio")}</th>
            {data.exercices.map((e) => <th key={e.periode} scope="col" className="py-1 pr-3 text-right">{e.exercice} ({e.periode})</th>)}
          </tr>
        </thead>
        {families.map((f) => (
          <tbody key={f} className="divide-y divide-slate-100">
            <tr><th scope="rowgroup" colSpan={4} className="pt-3 text-left text-xs uppercase text-slate-500">{t(`ratios.familles.${f}`, { defaultValue: f })}</th></tr>
            {data.ratios.filter((r) => (r.famille ?? "autres") === f).map((r) => (
              <tr key={r.code}>
                <th scope="row" className="py-1 pr-3 font-normal">{r.libelle}</th>
                {data.exercices.map((e) => {
                  const v = r.valeurs[e.periode];
                  return <td key={e.periode} className="py-1 pr-3 text-right font-mono">{v === null ? "—" : `${formatDecimal(v)}${unit(r.unite)}`}</td>;
                })}
              </tr>
            ))}
          </tbody>
        ))}
      </table>
      <p className="text-xs text-slate-500">{t("ratios.note")}</p>
    </section>
  );
}
