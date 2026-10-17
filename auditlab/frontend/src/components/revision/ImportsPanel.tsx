import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, tokenStore } from "../../api/client";
import { api } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDateHeure, formatNombre } from "../../lib/format";
import Alert from "../Alert";

export interface TrialBalance {
  id: string;
  periode: "N" | "N-1";
  type: string;
  logiciel: string;
  nom_fichier: string | null;
  statut: "accepte" | "rejete";
  anomalies: { code: string; message: string; compte?: string }[];
  avertissements: { code: string; message: string }[];
  totaux: Record<string, string | number>;
  nb_lignes: number;
  dataset_id: string | null;
  devise_source: string | null;
  cours: string | null;
  created_at: string | null;
  deleted_at: string | null;
}

const TYPES = ["balance", "grand_livre", "aux_clients", "aux_fournisseurs", "aux_cotisants", "aux_allocataires"];
const LOGICIELS = ["generique", "sage", "odoo", "perfecto", "saari"];

/** Import des balances, balances auxiliaires et grand livre (REV-05 à REV-07), avec le résultat des contrôles bloquants (REV-06). */
export default function ImportsPanel({ file, onChange }: { file: AuditFile; onChange?: () => void }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<TrialBalance[]>([]);
  const [form, setForm] = useState({ periode: "N", type: "balance", logiciel: "generique", compte_collectif: "", devise_source: "", date_cours: "" });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TrialBalance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback(() => api<TrialBalance[]>(`/audit-files/${file.id}/imports`).then(setItems), [file.id]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  const send = async (f: File) => {
    setBusy(true);
    setError(null);
    setResult(null);
    const body = new FormData();
    body.append("file", f);
    Object.entries(form).forEach(([k, v]) => v && body.append(k, v));
    try {
      const headers = new Headers();
      const token = tokenStore.get();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      const resp = await fetch(`/api/audit-files/${file.id}/imports`, { method: "POST", body, headers });
      const json = await resp.json();
      if (!resp.ok) throw new ApiError(resp.status, typeof json.detail === "string" ? json.detail : resp.statusText);
      setResult(json as TrialBalance);
      await load();
      onChange?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const active = items.filter((i) => !i.deleted_at && i.statut === "accepte");
  const shown = history ? items : active;
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });
  const aux = form.type.startsWith("aux_");

  return (
    <section className="carte space-y-3" aria-labelledby="imports-titre">
      <h2 id="imports-titre" className="text-base font-semibold">{t("balances.titre")}</h2>
      {file.peut_travailler && (
        <div className="grid gap-2 md:grid-cols-4">
          <div>
            <label htmlFor="bl-per" className="etiquette">{t("balances.periode")}</label>
            <select id="bl-per" className="champ" value={form.periode} onChange={set("periode")}>
              <option value="N">{t("balances.periodes.N", { exercice: file.exercice })}</option>
              <option value="N-1">{t("balances.periodes.N-1", { exercice: file.exercice - 1 })}</option>
            </select>
          </div>
          <div>
            <label htmlFor="bl-type" className="etiquette">{t("balances.type")}</label>
            <select id="bl-type" className="champ" value={form.type} onChange={set("type")}>{TYPES.map((x) => <option key={x} value={x}>{t(`balances.types.${x}`)}</option>)}</select>
          </div>
          <div>
            <label htmlFor="bl-log" className="etiquette">{t("balances.logiciel")}</label>
            <select id="bl-log" className="champ" value={form.logiciel} onChange={set("logiciel")}>{LOGICIELS.map((x) => <option key={x} value={x}>{t(`balances.logiciels.${x}`)}</option>)}</select>
          </div>
          {aux && (
            <div>
              <label htmlFor="bl-coll" className="etiquette">{t("balances.collectif")}</label>
              <input id="bl-coll" className="champ" inputMode="numeric" placeholder="411" value={form.compte_collectif} onChange={set("compte_collectif")} />
            </div>
          )}
          <div>
            <label htmlFor="bl-dev" className="etiquette">{t("balances.deviseSource", { devise: file.devise })}</label>
            <input id="bl-dev" className="champ" maxLength={3} placeholder={file.devise} value={form.devise_source} onChange={(e) => setForm({ ...form, devise_source: e.target.value.toUpperCase() })} />
          </div>
          {form.devise_source && form.devise_source !== file.devise && (
            <div>
              <label htmlFor="bl-date" className="etiquette">{t("balances.dateCours")}</label>
              <input id="bl-date" type="date" className="champ" value={form.date_cours} onChange={set("date_cours")} />
            </div>
          )}
          <div className="flex items-end md:col-span-4">
            <input ref={input} type="file" accept=".csv,.txt,.xlsx,.xls" className="hidden" tabIndex={-1} aria-hidden="true"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void send(f); e.target.value = ""; }} />
            <button type="button" className="btn-primaire" disabled={busy} onClick={() => input.current?.click()}>
              {busy ? t("balances.enCours") : t("balances.choisir")}
            </button>
          </div>
        </div>
      )}
      {error && <Alert kind="erreur">{error}</Alert>}
      {result && (
        <Alert kind={result.statut === "accepte" ? "succes" : "erreur"}>
          {result.statut === "accepte" ? t("balances.accepte", { n: formatNombre(result.nb_lignes) }) : t("balances.rejete")}
          {result.anomalies.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-sm">{result.anomalies.slice(0, 20).map((a, i) => <li key={i}>{a.message}</li>)}</ul>
          )}
          {result.anomalies.length > 20 && <p className="text-sm">{t("balances.autres", { n: result.anomalies.length - 20 })}</p>}
          {result.avertissements.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-sm text-amber-800" aria-label={t("balances.avertissements")}>
              {result.avertissements.map((a, i) => <li key={i}>{a.message}</li>)}
            </ul>
          )}
        </Alert>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600">
            <tr>{["donnee", "fichier", "lignes", "totaux", "statut", "date"].map((k) => <th key={k} scope="col" className="py-1 pr-3">{t(`balances.col.${k}`)}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.map((i) => (
              <tr key={i.id} className={i.deleted_at ? "text-slate-400" : ""}>
                <td className="py-1 pr-3">{t(`balances.types.${i.type}`)} {i.periode}</td>
                <td className="py-1 pr-3">{i.nom_fichier}{i.devise_source && ` (${i.devise_source} × ${i.cours})`}</td>
                <td className="py-1 pr-3 text-right">{formatNombre(i.nb_lignes)}</td>
                <td className="py-1 pr-3 font-mono text-xs">
                  {i.totaux.solde_debit !== undefined
                    ? `${formatNombre(Number(i.totaux.solde_debit))} / ${formatNombre(Number(i.totaux.solde_credit))}`
                    : `${formatNombre(Number(i.totaux.debit ?? 0))} / ${formatNombre(Number(i.totaux.credit ?? 0))}`}
                </td>
                <td className="py-1 pr-3">
                  {i.deleted_at ? t("balances.remplace") : t(`balances.statuts.${i.statut}`)}
                  {i.anomalies.length > 0 && <span className="ml-1 text-xs text-red-700">({t("balances.nbAnomalies", { n: i.anomalies.length })})</span>}
                  {i.avertissements.length > 0 && <span className="ml-1 text-xs text-amber-700" title={i.avertissements.map((a) => a.message).join("\n")}>({t("balances.nbAvertissements", { n: i.avertissements.length })})</span>}
                </td>
                <td className="py-1 text-xs">{formatDateHeure(i.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={history} onChange={(e) => setHistory(e.target.checked)} />
        {t("balances.historique")}
      </label>
    </section>
  );
}
