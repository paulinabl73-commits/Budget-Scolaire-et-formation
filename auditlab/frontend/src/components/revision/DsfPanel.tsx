import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, download } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

export interface DsfModelSummary { id: string; pays: string; nom: string; version: string; actif: boolean; feuilles: { nom: string; lignes: number }[] }
interface Sheet { nom: string; lignes: { ref: string; libelle: string; note: string | null; N: string | null; "N-1": string | null }[] }

/** Aide à la liasse fiscale et statistique depuis les états révisés (REV-25). */
export default function DsfPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [models, setModels] = useState<DsfModelSummary[]>([]);
  const [model, setModel] = useState("");
  const [sheets, setSheets] = useState<Sheet[]>([]);
  const [sheet, setSheet] = useState(0);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<DsfModelSummary[]>("/dsf-models").then((m) => {
      const active = m.filter((x) => x.actif);
      setModels(active);
      setModel(active[0]?.id ?? "");
    }).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!model) return;
    api<{ feuilles: Sheet[] }>(`/audit-files/${file.id}/dsf?model_id=${model}`).then((r) => { setSheets(r.feuilles); setSheet(0); }).catch((e: Error) => setError(e.message));
  }, [file.id, model]);
  const n = (v: string | null) => (v === null ? "" : formatNombre(Number(v)));

  return (
    <section className="carte space-y-3" aria-labelledby="dsf-titre">
      <h2 id="dsf-titre" className="text-base font-semibold">{t("dsf.titre")}</h2>
      <p className="text-sm text-slate-600">{t("dsf.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div className="flex flex-wrap items-end gap-2">
        <div><label htmlFor="dsf-modele" className="etiquette">{t("dsf.modele")}</label>
          <select id="dsf-modele" className="champ" value={model} onChange={(e) => setModel(e.target.value)}>{models.map((m) => <option key={m.id} value={m.id}>{m.pays} – {m.nom} ({m.version})</option>)}</select></div>
        <div><label htmlFor="dsf-feuille" className="etiquette">{t("dsf.feuille")}</label>
          <select id="dsf-feuille" className="champ" value={sheet} onChange={(e) => setSheet(Number(e.target.value))}>{sheets.map((s, i) => <option key={s.nom} value={i}>{s.nom}</option>)}</select></div>
        <button type="button" className="btn-secondaire" disabled={!model} onClick={() => void download(`/audit-files/${file.id}/dsf/export?model_id=${model}`, undefined, "dsf.xlsx").catch((e: Error) => setError(e.message))}>{t("dsf.exporter")}</button>
      </div>
      {sheets[sheet] && (
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-600"><tr>{["ref", "libelle", "note", "N", "N-1"].map((k) => <th key={k} scope="col" className="py-1 pr-3 text-left">{t(`dsf.col.${k}`)}</th>)}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {sheets[sheet].lignes.map((l) => <tr key={l.ref}><td className="py-1 pr-3 font-mono text-xs">{l.ref}</td><td className="py-1 pr-3">{l.libelle}</td><td className="py-1 pr-3">{l.note}</td><td className="py-1 pr-3 text-right font-mono">{n(l.N)}</td><td className="py-1 text-right font-mono">{n(l["N-1"])}</td></tr>)}
          </tbody>
        </table>
      )}
    </section>
  );
}
