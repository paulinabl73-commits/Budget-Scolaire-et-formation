import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";
import AdjustmentsPanel from "./AdjustmentsPanel";

interface Line { code: string; libelle: string; niveau: number; passage: string | null; total: boolean; N: string; "N-1": string | null }
interface Rec { lignes: { libelle: string; montant: string }[]; ifrs: string; ecart: string }
interface Ifrs {
  referentiel: string;
  etats: Record<string, Line[]>;
  controles: { code: string; libelle: string; ok: boolean; ecarts: Record<string, string> }[];
  reconciliation: { capitaux: Rec; resultat: Rec };
}

/** Passage aux IFRS : retraitements (IFR-01), états et réconciliations (IFR-03). */
export default function IfrsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Ifrs | null>(null);
  const [etat, setEtat] = useState("ifrs_situation");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setData(await api<Ifrs>(`/audit-files/${file.id}/ifrs`));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [file.id]);
  useEffect(() => {
    void load();
  }, [load]);
  const n = (v: string | null) => (v === null ? "" : formatNombre(Number(v)));

  return (
    <div className="space-y-4">
      <AdjustmentsPanel file={file} ifrs onChange={() => void load()} />
      {error && <Alert kind="info">{error}</Alert>}
      {data && (
        <section className="carte space-y-3" aria-labelledby="ifrs-titre">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div><h2 id="ifrs-titre" className="text-base font-semibold">{t("ifrs.titre")}</h2><p className="text-xs text-slate-600">{data.referentiel}</p></div>
            <div className="flex gap-2">{["pdf", "docx"].map((fmt) => <button key={fmt} type="button" className="btn-secondaire" onClick={() => void download(`/audit-files/${file.id}/ifrs/export?format=${fmt}`, undefined, `etats_ifrs.${fmt}`).catch((e: Error) => setError(e.message))}>{t(`ifrs.export.${fmt}`)}</button>)}</div>
          </div>
          <ul className="text-sm">{data.controles.map((c) => <li key={c.code} className={c.ok ? "text-emerald-800" : "text-red-700"}>{c.ok ? "✓" : "✗"} {c.libelle}</li>)}</ul>
          <div role="tablist" className="flex flex-wrap gap-1 border-b border-slate-200">
            {Object.keys(data.etats).map((k) => <button key={k} type="button" role="tab" aria-selected={k === etat} onClick={() => setEtat(k)} className={`-mb-px border-b-2 px-3 py-1 text-sm ${k === etat ? "border-marque-600 text-marque-700" : "border-transparent text-slate-600"}`}>{t(`ifrs.etats.${k}`)}</button>)}
          </div>
          <table className="w-full text-sm" role="tabpanel">
            <thead className="text-xs text-slate-600"><tr><th scope="col" className="py-1 pr-3 text-left">{t("ifrs.poste")}</th><th scope="col" className="py-1 pr-3 text-left">{t("ifrs.passage")}</th><th scope="col" className="py-1 pr-3 text-right">N</th><th scope="col" className="py-1 text-right">N-1</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {(data.etats[etat] ?? []).map((l) => (
                <tr key={l.code} className={l.total ? "bg-slate-50 font-semibold" : ""}><td className="py-1 pr-3">{l.libelle}</td><td className="py-1 pr-3 font-mono text-xs text-slate-500">{l.passage}</td><td className="py-1 pr-3 text-right font-mono">{n(l.N)}</td><td className="py-1 text-right font-mono">{n(l["N-1"])}</td></tr>
              ))}
            </tbody>
          </table>
          <div className="grid gap-4 md:grid-cols-2">
            {(["capitaux", "resultat"] as const).map((k) => (
              <table key={k} className="w-full text-sm">
                <caption className="text-left font-semibold">{t(`ifrs.reconciliation.${k}`)}</caption>
                <tbody className="divide-y divide-slate-100">
                  {data.reconciliation[k].lignes.map((r) => <tr key={r.libelle}><td className="py-1 pr-3">{r.libelle}</td><td className="py-1 text-right font-mono">{n(r.montant)}</td></tr>)}
                  <tr className="font-semibold"><td className="py-1 pr-3">{t("ifrs.montantIfrs")}</td><td className="py-1 text-right font-mono">{n(data.reconciliation[k].ifrs)}</td></tr>
                  {Number(data.reconciliation[k].ecart) !== 0 && <tr className="text-red-700"><td className="py-1 pr-3">{t("ifrs.ecart")}</td><td className="py-1 text-right font-mono">{n(data.reconciliation[k].ecart)}</td></tr>}
                </tbody>
              </table>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
