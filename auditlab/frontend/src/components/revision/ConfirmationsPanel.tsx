import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, download, patch, post } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDate, formatNombre } from "../../lib/format";
import Alert from "../Alert";

interface Conf {
  id: string; numero: number; reference: string; type: string; tiers: string; compte: string | null;
  adresse: string | null; solde_comptable: string | null; statut: string; envoyee_le: string | null;
  reponse_le: string | null; solde_confirme: string | null; ecart: string | null; explication: string | null;
  procedure_alternative: string | null;
}
interface Stats { envoyees: number; recues: number; taux_reponse: number | null; ecarts: number; ecarts_non_expliques: number }
const TYPES = ["banque", "client", "fournisseur", "avocat"] as const;
const num = (v: string) => v.replace(/\s/g, "").replace(",", ".");

/** Circularisation : sélection, lettres PDF et Word, suivi des réponses et des écarts (REV-19). */
export default function ConfirmationsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Conf[]>([]);
  const [stats, setStats] = useState<Record<string, Stats>>({});
  const [kind, setKind] = useState<string>("client");
  const [seuil, setSeuil] = useState("");
  const [manual, setManual] = useState({ type: "avocat", tiers: "", adresse: "" });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const base = `/audit-files/${file.id}/confirmations`;
  const load = useCallback(async () => {
    const r = await api<{ confirmations: Conf[]; synthese: Record<string, Stats> }>(base);
    setItems(r.confirmations);
    setStats(r.synthese);
  }, [base]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const run = async (fn: () => Promise<unknown>, message?: (r: never) => string) => {
    setError(null);
    setInfo(null);
    try {
      const r = await fn();
      if (message) setInfo(message(r as never));
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const select = () =>
    run(() => post(`${base}/select`, { type: kind, seuil: seuil ? num(seuil) : null }), (r: { ajoutees: number }) => t("circularisation.ajoutees", { n: r.ajoutees }));
  const add = (e: FormEvent) => {
    e.preventDefault();
    void run(() => post(base, { ...manual, adresse: manual.adresse || null }));
    setManual({ ...manual, tiers: "", adresse: "" });
  };
  const n = (v: string | null) => (v === null ? "" : formatNombre(Number(v)));

  return (
    <section className="carte space-y-3" aria-labelledby="circ-titre">
      <h2 id="circ-titre" className="text-base font-semibold">{t("circularisation.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {info && <Alert kind="succes">{info}</Alert>}
      <dl className="grid gap-2 text-sm md:grid-cols-4">
        {TYPES.map((k) => stats[k] && (
          <div key={k} className="rounded border border-slate-200 p-2">
            <dt className="text-xs text-slate-600">{t(`circularisation.types.${k}`)}</dt>
            <dd>{t("circularisation.stats", { envoyees: stats[k].envoyees, recues: stats[k].recues, taux: stats[k].taux_reponse ?? "—" })}</dd>
            {stats[k].ecarts > 0 && <dd className="text-xs text-amber-800">{t("circularisation.ecarts", { n: stats[k].ecarts, restant: stats[k].ecarts_non_expliques })}</dd>}
          </div>
        ))}
      </dl>
      {file.peut_travailler && (
        <div className="flex flex-wrap items-end gap-2">
          <div><label htmlFor="circ-type" className="etiquette">{t("circularisation.type")}</label>
            <select id="circ-type" className="champ" value={kind} onChange={(e) => setKind(e.target.value)}>{["client", "fournisseur", "banque"].map((k) => <option key={k} value={k}>{t(`circularisation.types.${k}`)}</option>)}</select></div>
          {kind !== "banque" && <div><label htmlFor="circ-seuil" className="etiquette">{t("circularisation.seuil")}</label><input id="circ-seuil" className="champ" inputMode="decimal" placeholder={t("circularisation.seuilDefaut")} value={seuil} onChange={(e) => setSeuil(e.target.value)} /></div>}
          <button type="button" className="btn-primaire" onClick={() => void select()}>{t("circularisation.selectionner")}</button>
          <button type="button" className="btn-secondaire" onClick={() => void download(`${base}/letters?format=pdf`, undefined, "circularisation.pdf").catch((e: Error) => setError(e.message))}>{t("circularisation.lettresPdf")}</button>
          <button type="button" className="btn-secondaire" onClick={() => void download(`${base}/letters?format=docx`, undefined, "circularisation.docx").catch((e: Error) => setError(e.message))}>{t("circularisation.lettresWord")}</button>
        </div>
      )}
      {file.peut_travailler && (
        <form onSubmit={add} className="flex flex-wrap items-end gap-2">
          <div><label htmlFor="circ-mt" className="etiquette">{t("circularisation.ajoutManuel")}</label><select id="circ-mt" className="champ" value={manual.type} onChange={(e) => setManual({ ...manual, type: e.target.value })}>{TYPES.map((k) => <option key={k} value={k}>{t(`circularisation.types.${k}`)}</option>)}</select></div>
          <div><label htmlFor="circ-tiers" className="etiquette">{t("circularisation.destinataire")}</label><input id="circ-tiers" className="champ" required value={manual.tiers} onChange={(e) => setManual({ ...manual, tiers: e.target.value })} /></div>
          <div><label htmlFor="circ-adr" className="etiquette">{t("circularisation.adresse")}</label><input id="circ-adr" className="champ" value={manual.adresse} onChange={(e) => setManual({ ...manual, adresse: e.target.value })} /></div>
          <button type="submit" className="btn-secondaire">{t("circularisation.ajouter")}</button>
        </form>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-600"><tr>{["ref", "tiers", "comptable", "statut", "confirme", "ecart", "actions"].map((k) => <th key={k} scope="col" className="py-1 pr-3 text-left">{t(`circularisation.col.${k}`)}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100 align-top">
            {items.map((c) => (
              <tr key={c.id} className={c.ecart && Number(c.ecart) !== 0 && !c.explication ? "bg-amber-50" : ""}>
                <td className="py-1 pr-3 font-mono text-xs">{c.reference}</td>
                <td className="py-1 pr-3">{c.tiers}<span className="block text-xs text-slate-500">{t(`circularisation.types.${c.type}`)}{c.compte && ` · ${c.compte}`}</span></td>
                <td className="py-1 pr-3 text-right font-mono">{n(c.solde_comptable)}</td>
                <td className="py-1 pr-3">{t(`circularisation.statuts.${c.statut}`)}{c.envoyee_le && <span className="block text-xs text-slate-500">{formatDate(c.envoyee_le)}</span>}</td>
                <td className="py-1 pr-3 text-right font-mono">{n(c.solde_confirme)}</td>
                <td className="py-1 pr-3 text-right font-mono">{n(c.ecart)}{c.explication && <span className="block max-w-xs text-left font-sans text-xs text-slate-600">{c.explication}</span>}</td>
                <td className="py-1 text-xs">
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className="underline" onClick={() => void download(`/confirmations/${c.id}/letter?format=docx`, undefined, `${c.reference}.docx`).catch((e: Error) => setError(e.message))}>{t("circularisation.lettre")}</button>
                    {file.peut_travailler && c.statut === "a_envoyer" && <button type="button" className="underline" onClick={() => void run(() => patch(`/confirmations/${c.id}`, { statut: "envoyee" }))}>{t("circularisation.envoyee")}</button>}
                    {file.peut_travailler && c.statut === "a_envoyer" && <button type="button" className="text-red-700 underline" onClick={() => void run(() => del(`/confirmations/${c.id}`))}>{t("circularisation.supprimer")}</button>}
                    {file.peut_travailler && c.statut !== "a_envoyer" && c.type !== "avocat" && (
                      <span className="flex items-center gap-1">
                        <input className="champ w-28" aria-label={t("circularisation.saisirReponse", { ref: c.reference })} inputMode="decimal" value={answers[c.id] ?? ""} onChange={(e) => setAnswers({ ...answers, [c.id]: e.target.value })} />
                        <button type="button" className="underline" onClick={() => void run(() => patch(`/confirmations/${c.id}`, { solde_confirme: num(answers[c.id] ?? "") }))}>{t("circularisation.enregistrer")}</button>
                      </span>
                    )}
                    {file.peut_travailler && c.ecart && Number(c.ecart) !== 0 && <button type="button" className="underline" onClick={() => void run(() => post(`/confirmations/${c.id}/reconcile`), (r: { message?: string }) => r.message ?? t("circularisation.rapproche"))}>{t("circularisation.rapprocher")}</button>}
                    {file.peut_travailler && (c.statut === "envoyee" || c.statut === "relancee") && <button type="button" className="underline" onClick={() => void run(() => patch(`/confirmations/${c.id}`, { statut: "sans_reponse" }))}>{t("circularisation.sansReponse")}</button>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
