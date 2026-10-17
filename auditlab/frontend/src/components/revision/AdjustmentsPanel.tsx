import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, del, post, put } from "../../api/client";
import type { AuditFile, WorkpaperSummary } from "../../api/types";
import { formatDateHeure, formatNombre } from "../../lib/format";
import Alert from "../Alert";

export interface AdjustmentLine { compte: string; libelle: string | null; debit: string; credit: string }
export interface Adjustment {
  id: string;
  numero: number;
  type: "correction" | "reclassement";
  libelle: string;
  justification: string;
  workpaper_id: string | null;
  statut: "proposee" | "acceptee" | "refusee";
  motif_decision: string | null;
  decision_le: string | null;
  decision_par: string | null;
  lignes: AdjustmentLine[];
  total: string;
  effet_resultat: string;
}

const EMPTY = { type: "correction", libelle: "", justification: "", workpaper_id: "", lignes: [{ compte: "", libelle: "", debit: "", credit: "" }, { compte: "", libelle: "", debit: "", credit: "" }] };
const num = (v: string) => v.replace(/\s/g, "").replace(",", ".");

/** Propositions d'écritures d'ajustement (REV-21). */
export default function AdjustmentsPanel({ file, onChange }: { file: AuditFile; onChange?: () => void }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Adjustment[]>([]);
  const [papers, setPapers] = useState<WorkpaperSummary[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [motifs, setMotifs] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => setItems(await api<Adjustment[]>(`/audit-files/${file.id}/adjustments`)), [file.id]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
    api<WorkpaperSummary[]>(`/engagements/${file.engagement_id}/workpapers`).then(setPapers).catch(() => setPapers([]));
  }, [load, file.engagement_id]);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
      onChange?.();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = {
      ...form,
      workpaper_id: form.workpaper_id || null,
      lignes: form.lignes.filter((l) => l.compte).map((l) => ({ compte: l.compte, libelle: l.libelle || null, debit: num(l.debit) || "0", credit: num(l.credit) || "0" })),
    };
    const ok = await run(() => (editing ? put(`/adjustments/${editing}`, body) : post(`/audit-files/${file.id}/adjustments`, body)));
    if (ok) {
      setForm(EMPTY);
      setEditing(null);
      setShowForm(false);
    }
  };
  const edit = (a: Adjustment) => {
    setEditing(a.id);
    setShowForm(true);
    setForm({ type: a.type, libelle: a.libelle, justification: a.justification, workpaper_id: a.workpaper_id ?? "", lignes: a.lignes.map((l) => ({ compte: l.compte, libelle: l.libelle ?? "", debit: l.debit === "0.00" ? "" : l.debit, credit: l.credit === "0.00" ? "" : l.credit })) });
  };
  const setLine = (i: number, k: keyof AdjustmentLine, v: string) => setForm({ ...form, lignes: form.lignes.map((l, j) => (j === i ? { ...l, [k]: v } : l)) });
  const sum = (k: "debit" | "credit") => form.lignes.reduce((s, l) => s + (Number(num(l[k])) || 0), 0);
  const paper = (id: string | null) => papers.find((p) => p.id === id);

  return (
    <section className="carte space-y-3" aria-labelledby="aje-titre">
      <div className="flex items-center justify-between gap-2">
        <h2 id="aje-titre" className="text-base font-semibold">{t("ajustements.titre")}</h2>
        {file.peut_travailler && !showForm && <button type="button" className="btn-primaire" onClick={() => { setForm(EMPTY); setEditing(null); setShowForm(true); }}>{t("ajustements.nouvelle")}</button>}
      </div>
      {error && <Alert kind="erreur">{error}</Alert>}
      {showForm && (
        <form onSubmit={submit} className="space-y-2 rounded border border-slate-200 p-3">
          <div className="grid gap-2 md:grid-cols-4">
            <div><label htmlFor="aje-type" className="etiquette">{t("ajustements.type")}</label><select id="aje-type" className="champ" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}><option value="correction">{t("ajustements.types.correction")}</option><option value="reclassement">{t("ajustements.types.reclassement")}</option></select></div>
            <div className="md:col-span-2"><label htmlFor="aje-lib" className="etiquette">{t("ajustements.libelle")}</label><input id="aje-lib" className="champ" required value={form.libelle} onChange={(e) => setForm({ ...form, libelle: e.target.value })} /></div>
            <div><label htmlFor="aje-wp" className="etiquette">{t("ajustements.papier")}</label><select id="aje-wp" className="champ" value={form.workpaper_id} onChange={(e) => setForm({ ...form, workpaper_id: e.target.value })}><option value="">—</option>{papers.map((p) => <option key={p.id} value={p.id}>{p.reference} – {p.titre}</option>)}</select></div>
            <div className="md:col-span-4"><label htmlFor="aje-just" className="etiquette">{t("ajustements.justification")}</label><textarea id="aje-just" rows={2} className="champ" required minLength={10} value={form.justification} onChange={(e) => setForm({ ...form, justification: e.target.value })} /></div>
          </div>
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-600"><tr>{["compte", "libelleLigne", "debit", "credit"].map((k) => <th key={k} scope="col" className="py-1 pr-2 text-left">{t(`ajustements.col.${k}`)}</th>)}<th /></tr></thead>
            <tbody>
              {form.lignes.map((l, i) => (
                <tr key={i}>
                  {(["compte", "libelle", "debit", "credit"] as const).map((k) => (
                    <td key={k} className="py-1 pr-2"><input className="champ" aria-label={t(`ajustements.ligne.${k}`, { n: i + 1 })} inputMode={k === "compte" || k === "libelle" ? undefined : "decimal"} value={l[k] ?? ""} onChange={(e) => setLine(i, k, e.target.value)} /></td>
                  ))}
                  <td>{form.lignes.length > 2 && <button type="button" className="text-xs underline" onClick={() => setForm({ ...form, lignes: form.lignes.filter((_, j) => j !== i) })}>{t("ajustements.retirer")}</button>}</td>
                </tr>
              ))}
              <tr className="text-xs text-slate-600">
                <td colSpan={2}><button type="button" className="underline" onClick={() => setForm({ ...form, lignes: [...form.lignes, { compte: "", libelle: "", debit: "", credit: "" }] })}>{t("ajustements.ajouterLigne")}</button></td>
                <td className={sum("debit") === sum("credit") ? "" : "text-red-700"}>{formatNombre(sum("debit"))}</td>
                <td className={sum("debit") === sum("credit") ? "" : "text-red-700"}>{formatNombre(sum("credit"))}</td>
              </tr>
            </tbody>
          </table>
          <div className="flex gap-2"><button type="submit" className="btn-primaire">{editing ? t("commun.enregistrer") : t("ajustements.proposer")}</button><button type="button" className="btn-secondaire" onClick={() => setShowForm(false)}>{t("commun.annuler")}</button></div>
        </form>
      )}
      {items.length === 0 ? <p className="text-sm text-slate-600">{t("ajustements.aucune")}</p> : (
        <ul className="divide-y divide-slate-100">
          {items.map((a) => (
            <li key={a.id} className="space-y-1 py-2 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p><strong>AJE {a.numero}</strong> · {t(`ajustements.types.${a.type}`)} · {a.libelle}</p>
                <span className={`rounded px-2 text-xs ${a.statut === "acceptee" ? "bg-emerald-100 text-emerald-800" : a.statut === "refusee" ? "bg-red-100 text-red-800" : "bg-slate-100"}`}>{t(`ajustements.statuts.${a.statut}`)}</span>
              </div>
              <p className="text-slate-600">{a.justification}{paper(a.workpaper_id) && <> · <Link className="underline" to={`/missions/${file.engagement_id}/papiers/${a.workpaper_id}`}>{paper(a.workpaper_id)?.reference}</Link></>}</p>
              <table className="text-xs"><tbody>{a.lignes.map((l, i) => <tr key={i}><td className="pr-3 font-mono">{l.compte}</td><td className="pr-3">{l.libelle}</td><td className="pr-3 text-right font-mono">{l.debit !== "0.00" ? formatNombre(Number(l.debit)) : ""}</td><td className="text-right font-mono">{l.credit !== "0.00" ? formatNombre(Number(l.credit)) : ""}</td></tr>)}</tbody></table>
              <p className="text-xs text-slate-600">{t("ajustements.effet", { montant: formatNombre(Number(a.effet_resultat)) })}{a.decision_le && ` · ${t("ajustements.decision", { par: a.decision_par, date: formatDateHeure(a.decision_le) })}`}{a.motif_decision && ` · ${a.motif_decision}`}</p>
              {file.peut_travailler && a.statut === "proposee" && (
                <div className="flex flex-wrap items-end gap-2">
                  <button type="button" className="btn-secondaire" onClick={() => void run(() => post(`/adjustments/${a.id}/decision`, { statut: "acceptee" }))}>{t("ajustements.accepter")}</button>
                  <input className="champ max-w-xs" aria-label={t("ajustements.motif", { n: a.numero })} placeholder={t("ajustements.motifPlaceholder")} value={motifs[a.id] ?? ""} onChange={(e) => setMotifs({ ...motifs, [a.id]: e.target.value })} />
                  <button type="button" className="btn-secondaire" onClick={() => void run(() => post(`/adjustments/${a.id}/decision`, { statut: "refusee", motif: motifs[a.id] }))}>{t("ajustements.refuser")}</button>
                  <button type="button" className="text-xs underline" onClick={() => edit(a)}>{t("ajustements.modifier")}</button>
                  <button type="button" className="text-xs text-red-700 underline" onClick={() => void run(() => del(`/adjustments/${a.id}`))}>{t("ajustements.supprimer")}</button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
