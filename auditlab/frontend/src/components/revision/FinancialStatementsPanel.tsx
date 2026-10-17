import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Line { code: string; libelle: string; niveau: number; total: boolean; N_avant: string; ajustements: string; N: string; "N-1": string | null }
interface Check { code: string; libelle: string; ecarts: Record<string, string>; ok: boolean }
interface Statements { referentiel: string; etats: Record<string, Line[]>; controles: Check[]; controles_avant: Check[] }

/** États financiers révisés avant et après ajustements (REV-23), contrôles (REV-24). */
export default function FinancialStatementsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Statements | null>(null);
  const [etat, setEtat] = useState<string>("bilan_actif");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Statements>(`/audit-files/${file.id}/statements`).then(setData).catch((e: Error) => setError(e.message));
  }, [file.id]);
  if (error && !data) return <Alert kind="erreur">{error}</Alert>;
  if (!data) return null;
  const n = (v: string | null) => (v === null ? "" : formatNombre(Number(v)));
  const exportAs = (format: "xlsx" | "pdf") =>
    download(`/audit-files/${file.id}/statements/export?format=${format}`, undefined, `etats_financiers.${format}`).catch((e: Error) => setError(e.message));
  const ok = data.controles.every((c) => c.ok);

  return (
    <section className="carte space-y-3" aria-labelledby="ef-titre">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="ef-titre" className="text-base font-semibold">{t("etats.titre")}</h2>
          <p className="text-xs text-slate-600">{data.referentiel}</p>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn-secondaire" disabled={!ok} onClick={() => void exportAs("xlsx")}>{t("etats.excel")}</button>
          <button type="button" className="btn-secondaire" disabled={!ok} onClick={() => void exportAs("pdf")}>{t("etats.pdf")}</button>
        </div>
      </div>
      {error && <Alert kind="erreur">{error}</Alert>}
      <ul className="text-sm" aria-label={t("etats.controles")}>
        {data.controles.map((c) => (
          <li key={c.code} className={c.ok ? "text-emerald-800" : "text-red-700"}>
            {c.ok ? "✓" : "✗"} {c.libelle}
            {!c.ok && ` — ${Object.entries(c.ecarts).map(([p, v]) => `${p} : ${n(v)}`).join(" ; ")}`}
          </li>
        ))}
      </ul>
      {!ok && <p className="text-sm text-red-700">{t("etats.exportBloque")}</p>}
      <div role="tablist" className="flex flex-wrap gap-1 border-b border-slate-200">
        {Object.keys(data.etats).map((k) => (
          <button key={k} type="button" role="tab" aria-selected={k === etat} onClick={() => setEtat(k)}
            className={`-mb-px border-b-2 px-3 py-1 text-sm ${k === etat ? "border-marque-600 text-marque-700" : "border-transparent text-slate-600"}`}>
            {t(`affectation.etats.${k}`, { defaultValue: k })}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto" role="tabpanel">
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-600">
            <tr><th scope="col" className="py-1 pr-3 text-left">{t("etats.poste")}</th>{(["N_avant", "ajustements", "N", "N-1"] as const).map((k) => <th key={k} scope="col" className="py-1 pr-3 text-right">{t(`etats.col.${k}`)}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(data.etats[etat] ?? []).map((l) => (
              <tr key={l.code} className={l.total ? "bg-slate-50 font-semibold" : ""}>
                <td className="py-1 pr-3"><span className="font-mono text-xs">{l.code}</span> {l.libelle}</td>
                <td className="py-1 pr-3 text-right font-mono">{n(l.N_avant)}</td>
                <td className="py-1 pr-3 text-right font-mono">{Number(l.ajustements) ? n(l.ajustements) : ""}</td>
                <td className="py-1 pr-3 text-right font-mono">{n(l.N)}</td>
                <td className="py-1 text-right font-mono">{n(l["N-1"])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {etat === "flux_tresorerie" && <p className="text-xs text-slate-500">{t("etats.noteFlux")}</p>}
    </section>
  );
}
