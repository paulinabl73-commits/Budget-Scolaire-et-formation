import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api, del, post } from "../../api/client";
import type { Attachment, Dataset, WorkpaperSummary } from "../../api/types";
import { formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

interface Evidence {
  id: string;
  type: "papier" | "piece_jointe" | "table" | "lignes";
  workpaper_id: string | null;
  attachment_id: string | null;
  dataset_id: string | null;
  empreinte: string | null;
  empreinte_actuelle: string | null;
  extrait: { colonnes?: string[]; lignes?: unknown[][]; nb_lignes?: number };
  commentaire: string | null;
  libelle: string | null;
  created_at: string | null;
}

/** Preuves du constat (CON-03) : papiers, pièces jointes, résultats d'analyse, lignes (DAT-31). */
export default function EvidencePanel({ findingId, missionId, papers, editable }: { findingId: string; missionId: string; papers: WorkpaperSummary[]; editable: boolean }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Evidence[]>([]);
  const [type, setType] = useState<"papier" | "piece_jointe" | "table">("papier");
  const [wp, setWp] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [target, setTarget] = useState("");
  const [tables, setTables] = useState<Dataset[]>([]);
  const [commentaire, setCommentaire] = useState("");
  const [error, setError] = useState<string | null>(null);
  const url = `/findings/${findingId}/evidence`;
  const load = useCallback(() => api<Evidence[]>(url).then(setItems), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  useEffect(() => {
    if (type === "table") api<Dataset[]>(`/engagements/${missionId}/datasets`).then(setTables).catch(() => setTables([]));
  }, [type, missionId]);
  useEffect(() => {
    if (type === "piece_jointe" && wp) api<Attachment[]>(`/workpapers/${wp}/attachments`).then(setAttachments).catch(() => setAttachments([]));
  }, [type, wp]);

  const add = async () => {
    setError(null);
    const body: Record<string, unknown> = { type, commentaire: commentaire || null };
    if (type === "papier") body.workpaper_id = wp;
    if (type === "piece_jointe") body.attachment_id = target;
    if (type === "table") body.dataset_id = target;
    try {
      await post(url, body);
      setCommentaire("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const ready = type === "papier" ? !!wp : !!target;
  return (
    <section className="carte space-y-3" aria-labelledby="preuves-titre">
      <h2 id="preuves-titre" className="text-base font-semibold">{t("preuves.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {items.length === 0 && <p className="text-sm text-slate-600">{t("preuves.aucune")}</p>}
      <ul className="space-y-2">
        {items.map((e) => (
          <li key={e.id} className="text-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs">{t(`preuves.types.${e.type}`)}</span>
                {e.dataset_id ? (
                  <Link className="text-marque-700 underline" to={`/missions/${missionId}/donnees/${e.dataset_id}`}>{e.libelle}</Link>
                ) : e.workpaper_id ? (
                  <Link className="text-marque-700 underline" to={`/missions/${missionId}/papiers/${e.workpaper_id}`}>{e.libelle}</Link>
                ) : e.libelle}
                <span className="text-slate-500"> · {formatDateHeure(e.created_at)}</span>
                {e.commentaire && <p className="text-slate-700">{e.commentaire}</p>}
                {e.empreinte && <p className="font-mono text-xs text-slate-500">SHA-256 : {e.empreinte}</p>}
                {e.empreinte && e.empreinte_actuelle && e.empreinte !== e.empreinte_actuelle && (
                  <p className="text-xs text-red-700">{t("preuves.modifiee")}</p>
                )}
              </div>
              {editable && (
                <button type="button" className="text-xs text-red-700 underline" onClick={async () => { await del(`/evidence/${e.id}`); await load(); }}>
                  {t("analyses.retirer")}
                </button>
              )}
            </div>
            {e.type === "lignes" && e.extrait.colonnes && (
              <div className="mt-1 max-h-48 overflow-auto rounded border border-slate-200">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50"><tr>{e.extrait.colonnes.map((c) => <th key={c} scope="col" className="px-2 py-1 text-left">{c}</th>)}</tr></thead>
                  <tbody>
                    {(e.extrait.lignes ?? []).map((row, i) => (
                      <tr key={i} className="odd:bg-white even:bg-slate-50">{row.map((v, j) => <td key={j} className="px-2 py-0.5">{v === null ? "" : String(v)}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </li>
        ))}
      </ul>
      {editable && (
        <div className="grid gap-2 border-t border-slate-100 pt-2 md:grid-cols-4">
          <div>
            <label htmlFor="pv-type" className="etiquette">{t("preuves.type")}</label>
            <select id="pv-type" className="champ" value={type} onChange={(e) => { setType(e.target.value as typeof type); setTarget(""); }}>
              {(["papier", "piece_jointe", "table"] as const).map((k) => <option key={k} value={k}>{t(`preuves.types.${k}`)}</option>)}
            </select>
          </div>
          {type !== "table" && (
            <div>
              <label htmlFor="pv-wp" className="etiquette">{t("liens.papier")}</label>
              <select id="pv-wp" className="champ" value={wp} onChange={(e) => setWp(e.target.value)}>
                <option value="">—</option>
                {papers.map((p) => <option key={p.id} value={p.id}>{p.reference} · {p.titre}</option>)}
              </select>
            </div>
          )}
          {type === "piece_jointe" && (
            <div>
              <label htmlFor="pv-att" className="etiquette">{t("preuves.types.piece_jointe")}</label>
              <select id="pv-att" className="champ" value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">—</option>
                {attachments.map((a) => <option key={a.id} value={a.id}>{a.nom_fichier}</option>)}
              </select>
            </div>
          )}
          {type === "table" && (
            <div>
              <label htmlFor="pv-ds" className="etiquette">{t("preuves.types.table")}</label>
              <select id="pv-ds" className="champ" value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">—</option>
                {tables.filter((d) => d.statut === "pret").map((d) => <option key={d.id} value={d.id}>{d.nom}</option>)}
              </select>
            </div>
          )}
          <div>
            <label htmlFor="pv-com" className="etiquette">{t("liens.commentaire")}</label>
            <input id="pv-com" className="champ" value={commentaire} onChange={(e) => setCommentaire(e.target.value)} />
          </div>
          <div className="md:col-span-4">
            <button type="button" className="btn-secondaire" disabled={!ready} onClick={add}>{t("preuves.ajouter")}</button>
          </div>
        </div>
      )}
    </section>
  );
}
