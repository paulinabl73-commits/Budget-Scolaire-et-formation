import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, post, put } from "../../api/client";
import type { AuditFile, WorkpaperSummary } from "../../api/types";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

type Amounts = { "N-1": string; N: string; ajustements: string; revise: string };
interface Sheet {
  cycle: string;
  libelle: string;
  totaux: Amounts;
  comptes: ({ compte: string; libelle: string | null } & Amounts)[];
  papiers: { id: string; reference: string; titre: string; rattache: boolean }[];
  ecritures: { numero: number; statut: string }[];
}
const COLS = ["N-1", "N", "ajustements", "revise"] as const;

/** Feuilles maîtresses par cycle (REV-15). */
export default function LeadSchedulesPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [sheets, setSheets] = useState<Sheet[]>([]);
  const [papers, setPapers] = useState<WorkpaperSummary[]>([]);
  const [cycle, setCycle] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/lead-schedules`;
  useEffect(() => {
    api<Sheet[]>(url).then(setSheets).catch((e: Error) => setError(e.message));
    api<WorkpaperSummary[]>(`/engagements/${file.engagement_id}/workpapers`).then(setPapers).catch(() => setPapers([]));
  }, [url, file.engagement_id]);
  const sheet = sheets.find((s) => s.cycle === cycle);
  const toggle = async (id: string, on: boolean) => {
    if (!sheet) return;
    const ids = sheet.papiers.filter((p) => p.rattache).map((p) => p.id).filter((x) => x !== id);
    try {
      setSheets(await put<Sheet[]>(`${url}/${sheet.cycle}/workpapers`, { workpaper_ids: on ? [...ids, id] : ids }));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const amount = (v: string) => formatNombre(Number(v));

  return (
    <section className="carte space-y-3" aria-labelledby="fm-titre">
      <h2 id="fm-titre" className="text-base font-semibold">{t("feuilles.titre")}</h2>
      <p className="text-sm text-slate-600">{t("feuilles.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <table className="w-full text-sm">
        <thead className="text-xs text-slate-600">
          <tr><th scope="col" className="py-1 pr-3 text-left">{t("feuilles.cycle")}</th>{COLS.map((k) => <th key={k} scope="col" className="py-1 pr-3 text-right">{t(`feuilles.col.${k}`)}</th>)}<th scope="col" className="py-1 text-left">{t("feuilles.col.papiers")}</th></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {sheets.map((s) => (
            <tr key={s.cycle} className={s.cycle === cycle ? "bg-marque-50" : ""}>
              <th scope="row" className="py-1 pr-3 text-left font-normal"><button type="button" className="underline" onClick={() => setCycle(s.cycle === cycle ? null : s.cycle)} aria-expanded={s.cycle === cycle}>{s.libelle}</button></th>
              {COLS.map((k) => <td key={k} className="py-1 pr-3 text-right font-mono">{amount(s.totaux[k])}</td>)}
              <td className="py-1 text-xs">{s.papiers.map((p) => p.reference).join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {sheet && (
        <div className="space-y-2 rounded border border-slate-200 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">{t("feuilles.detail", { cycle: sheet.libelle })}</h3>
            {file.peut_gerer && (
              <button type="button" className="btn-secondaire" onClick={() => void post<{ procedures_ajoutees: number }>(`/audit-files/${file.id}/programs/${sheet.cycle}/apply`).then((r) => setInfo(t("programmes.applique", { n: r.procedures_ajoutees }))).catch((e: Error) => setError(e.message))}>
                {t("programmes.appliquer")}
              </button>
            )}
          </div>
          {info && <Alert kind="succes">{info}</Alert>}
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-600"><tr><th scope="col" className="py-1 pr-3 text-left">{t("feuilles.compte")}</th>{COLS.map((k) => <th key={k} scope="col" className="py-1 pr-3 text-right">{t(`feuilles.col.${k}`)}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">
              {sheet.comptes.map((c) => (
                <tr key={c.compte}><td className="py-1 pr-3"><span className="font-mono">{c.compte}</span> {c.libelle}</td>{COLS.map((k) => <td key={k} className="py-1 pr-3 text-right font-mono">{amount(c[k])}</td>)}</tr>
              ))}
              <tr className="font-semibold"><td className="py-1 pr-3">{t("feuilles.total")}</td>{COLS.map((k) => <td key={k} className="py-1 pr-3 text-right font-mono">{amount(sheet.totaux[k])}</td>)}</tr>
            </tbody>
          </table>
          {sheet.ecritures.length > 0 && (
            <p className="text-xs text-slate-600">{t("feuilles.ecritures")} {sheet.ecritures.map((e) => `AJE ${e.numero} (${t(`ajustements.statuts.${e.statut}`)})`).join(", ")}</p>
          )}
          <fieldset className="text-sm">
            <legend className="font-medium">{t("feuilles.renvois")}</legend>
            {papers.length === 0 && <p className="text-slate-600">{t("feuilles.aucunPapier")}</p>}
            {papers.map((p) => {
              const linked = sheet.papiers.find((x) => x.id === p.id);
              return (
                <label key={p.id} className="mr-4 inline-flex items-center gap-1">
                  <input type="checkbox" disabled={!file.peut_travailler} checked={!!linked?.rattache} onChange={(e) => void toggle(p.id, e.target.checked)} />
                  <Link className="underline" to={`/missions/${file.engagement_id}/papiers/${p.id}`}>{p.reference}</Link> {p.titre}
                  {linked && !linked.rattache && <span className="text-xs text-slate-500">({t("feuilles.viaAjustement")})</span>}
                </label>
              );
            })}
          </fieldset>
        </div>
      )}
    </section>
  );
}
