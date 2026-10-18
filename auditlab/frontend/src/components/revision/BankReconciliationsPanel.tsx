import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, tokenStore } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDate, formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Rec {
  id: string; compte: string; date_releve: string; nom_fichier: string | null; solde_releve: string; solde_comptable: string;
  non_rapproche: string; operations_releve: string; suspens_anciens: number; anomalies: string[]; avertissements: string[];
  suspens: { date: string | null; libelle: string | null; reference: string | null; origine: string; montant: string; ancien: boolean }[];
}
interface Overview { rapprochements: Rec[]; comptes_sans_rapprochement: string[] }

/** Rapprochements bancaires importés et contrôlés (REV-20). */
export default function BankReconciliationsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Overview | null>(null);
  const [form, setForm] = useState({ compte: "", solde_releve: "", date_releve: "" });
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const url = `/audit-files/${file.id}/bank-reconciliations`;
  const load = useCallback(async () => setData(await api<Overview>(url)), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const send = async () => {
    setError(null);
    const body = new FormData();
    Object.entries(form).forEach(([k, v]) => v && body.append(k, v));
    const f = input.current?.files?.[0];
    if (f) body.append("file", f);
    const headers = new Headers();
    const token = tokenStore.get();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const resp = await fetch(`/api${url}`, { method: "POST", body, headers });
    const json = await resp.json();
    if (!resp.ok) setError(typeof json.detail === "string" ? json.detail : resp.statusText);
    else {
      setData(json as Overview);
      if (input.current) input.current.value = "";
    }
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  const n = (v: string) => formatNombre(Number(v));

  return (
    <section className="carte space-y-3" aria-labelledby="rb-titre">
      <h2 id="rb-titre" className="text-base font-semibold">{t("rapprochements.titre")}</h2>
      <p className="text-sm text-slate-600">{t("rapprochements.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      {data.comptes_sans_rapprochement.length > 0 && <Alert kind="info">{t("rapprochements.manquants", { comptes: data.comptes_sans_rapprochement.join(", ") })}</Alert>}
      {file.peut_travailler && (
        <div className="grid gap-2 md:grid-cols-5">
          <div><label htmlFor="rb-compte" className="etiquette">{t("rapprochements.compte")}</label><input id="rb-compte" className="champ" list="rb-comptes" value={form.compte} onChange={(e) => setForm({ ...form, compte: e.target.value })} />
            <datalist id="rb-comptes">{data.comptes_sans_rapprochement.map((c) => <option key={c} value={c} />)}</datalist></div>
          <div><label htmlFor="rb-solde" className="etiquette">{t("rapprochements.soldeReleve")}</label><input id="rb-solde" className="champ" inputMode="decimal" value={form.solde_releve} onChange={(e) => setForm({ ...form, solde_releve: e.target.value })} /></div>
          <div><label htmlFor="rb-date" className="etiquette">{t("rapprochements.dateReleve")}</label><input id="rb-date" type="date" className="champ" value={form.date_releve} onChange={(e) => setForm({ ...form, date_releve: e.target.value })} /></div>
          <div><label htmlFor="rb-fichier" className="etiquette">{t("rapprochements.fichier")}</label><input id="rb-fichier" ref={input} type="file" accept=".csv,.txt,.xlsx" className="text-sm" /></div>
          <div className="flex items-end"><button type="button" className="btn-primaire" onClick={() => void send()}>{t("rapprochements.importer")}</button></div>
        </div>
      )}
      <table className="w-full text-sm">
        <thead className="text-xs text-slate-600"><tr>{["compte", "releve", "comptable", "nonRapproche", "controles"].map((k) => <th key={k} scope="col" className="py-1 pr-3 text-left">{t(`rapprochements.col.${k}`)}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100 align-top">
          {data.rapprochements.map((r) => (
            <tr key={r.id} className={r.anomalies.length ? "bg-red-50" : ""}>
              <td className="py-1 pr-3"><button type="button" className="font-mono underline" aria-expanded={open === r.id} onClick={() => setOpen(open === r.id ? null : r.id)}>{r.compte}</button><span className="block text-xs text-slate-500">{formatDate(r.date_releve)}</span></td>
              <td className="py-1 pr-3 text-right font-mono">{n(r.solde_releve)}</td>
              <td className="py-1 pr-3 text-right font-mono">{n(r.solde_comptable)}</td>
              <td className="py-1 pr-3 text-right font-mono">{n(r.non_rapproche)}</td>
              <td className="py-1 text-xs">{r.anomalies.map((a) => <p key={a} className="text-red-700">{a}</p>)}{r.avertissements.map((a) => <p key={a} className="text-amber-800">{a}</p>)}{!r.anomalies.length && !r.avertissements.length && "✓"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {open && (
        <table className="w-full text-xs">
          <caption className="text-left font-medium">{t("rapprochements.suspens")}</caption>
          <tbody>{data.rapprochements.find((r) => r.id === open)?.suspens.map((s, i) => (
            <tr key={i} className={s.ancien ? "text-red-700" : ""}><td className="pr-3">{formatDate(s.date)}</td><td className="pr-3">{s.reference}</td><td className="pr-3">{s.libelle}</td><td className="pr-3">{t(`rapprochements.origines.${s.origine}`)}</td><td className="text-right font-mono">{n(s.montant)}</td></tr>
          ))}</tbody>
        </table>
      )}
    </section>
  );
}
