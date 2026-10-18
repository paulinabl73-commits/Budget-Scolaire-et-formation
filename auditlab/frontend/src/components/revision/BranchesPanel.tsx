import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDecimal } from "../../lib/format";
import Alert from "../Alert";

interface Line { code: string; libelle: string; etat: string; niveau: number; N: string; "N-1": string }
interface Branches {
  branches: { code: string; libelle: string }[];
  comptes: { compte: string; libelle: string; solde_n: string; branche: string | null; origine: string | null }[];
  non_rattaches: string[];
  etats: Record<string, Line[]>;
  ratios: Record<string, { code: string; libelle: string; unite: string; N: string | null; "N-1": string | null }[]>;
  controles: { id: string; libelle: string; branche: string | null }[];
}

/** Suivi par branche d'un organisme de prévoyance sociale (CIP-01). */
export default function BranchesPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Branches | null>(null);
  const [branch, setBranch] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/branches`;
  useEffect(() => {
    api<Branches>(url).then((d) => { setData(d); setBranch((b) => b || d.branches[0]?.code || ""); }).catch((e: Error) => setError(e.message));
  }, [url]);
  const put = (path: string, branche: string) =>
    api<Branches>(`${url}/${path}`, { method: "PUT", body: JSON.stringify({ branche: branche || null }) }).then(setData).catch((e: Error) => setError(e.message));
  if (error) return <Alert kind="erreur">{error}</Alert>;
  if (!data) return null;
  const select = (value: string | null, onChange: (v: string) => void, label: string) => (
    <select aria-label={label} value={value ?? ""} disabled={!file.peut_travailler} onChange={(e) => onChange(e.target.value)} className="rounded border px-1 py-0.5">
      <option value="">{t("branches.aucune")}</option>
      {data.branches.map((b) => <option key={b.code} value={b.code}>{b.code} – {b.libelle}</option>)}
    </select>
  );
  return (
    <div className="space-y-4">
      {data.non_rattaches.length > 0 && <Alert kind="info">{t("branches.nonRattaches", { count: data.non_rattaches.length, comptes: data.non_rattaches.join(", ") })}</Alert>}
      <section className="carte space-y-3" aria-labelledby="branches-etats">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="branches-etats" className="text-base font-semibold">{t("branches.etats")}</h2>
          <div className="text-sm">
            <label htmlFor="branches-choix">{t("branches.branche")}</label>{" "}
            <select id="branches-choix" value={branch} onChange={(e) => setBranch(e.target.value)} className="rounded border px-1 py-0.5">
              {data.branches.map((b) => <option key={b.code} value={b.code}>{b.code} – {b.libelle}</option>)}
            </select>
          </div>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600">
            <tr><th scope="col" className="py-1 pr-3">{t("branches.poste")}</th><th scope="col" className="py-1 pr-3 text-right">N</th><th scope="col" className="py-1 pr-3 text-right">N-1</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(data.etats[branch] ?? []).map((l) => (
              <tr key={l.code} className={l.niveau === 1 ? "font-medium" : ""}>
                <th scope="row" className="py-1 pr-3 font-normal" style={{ paddingLeft: `${(l.niveau - 1) * 12}px` }}>{l.libelle}</th>
                <td className="py-1 pr-3 text-right font-mono">{formatDecimal(l.N)}</td>
                <td className="py-1 pr-3 text-right font-mono">{formatDecimal(l["N-1"])}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3 className="text-sm font-semibold">{t("branches.ratios")}</h3>
        <ul className="grid gap-1 text-sm sm:grid-cols-2">
          {(data.ratios[branch] ?? []).map((r) => (
            <li key={r.code} className="flex justify-between gap-2"><span>{r.libelle}</span><span className="font-mono">{r.N === null ? "—" : formatDecimal(r.N)}{r.unite === "pourcentage" && r.N !== null ? " %" : ""}</span></li>
          ))}
        </ul>
      </section>
      <section className="carte space-y-2" aria-labelledby="branches-comptes">
        <h2 id="branches-comptes" className="text-base font-semibold">{t("branches.comptes")}</h2>
        <p className="text-xs text-slate-500">{t("branches.aide")}</p>
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600">
            <tr><th scope="col" className="py-1 pr-3">{t("branches.compte")}</th><th scope="col" className="py-1 pr-3 text-right">{t("branches.solde")}</th><th scope="col" className="py-1 pr-3">{t("branches.branche")}</th><th scope="col" className="py-1 pr-3">{t("branches.origine")}</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.comptes.map((c) => (
              <tr key={c.compte}>
                <th scope="row" className="py-1 pr-3 font-normal"><span className="font-mono">{c.compte}</span> {c.libelle}</th>
                <td className="py-1 pr-3 text-right font-mono">{formatDecimal(c.solde_n)}</td>
                <td className="py-1 pr-3">{select(c.branche, (v) => void put(`accounts/${c.compte}`, v), t("branches.brancheDe", { compte: c.compte }))}</td>
                <td className="py-1 pr-3 text-xs text-slate-600">{c.origine ? t(`branches.origines.${c.origine}`) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="carte space-y-2" aria-labelledby="branches-controles">
        <h2 id="branches-controles" className="text-base font-semibold">{t("branches.controles")}</h2>
        {data.controles.length === 0 ? <p className="text-sm text-slate-600">{t("branches.aucunControle")}</p> : (
          <ul className="space-y-1 text-sm">
            {data.controles.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-2"><span>{c.libelle}</span>{select(c.branche, (v) => void put(`controls/${c.id}`, v), t("branches.brancheDe", { compte: c.libelle }))}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
