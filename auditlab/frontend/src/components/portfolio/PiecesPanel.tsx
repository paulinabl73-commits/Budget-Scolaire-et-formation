import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, download, patch, post } from "../../api/client";
import { formatDate } from "../../lib/format";
import Alert from "../Alert";

export interface Piece {
  id: string;
  libelle: string;
  categorie: string;
  date_limite: string;
  envoyee_le: string | null;
  recue_le: string | null;
  commentaire: string | null;
  relances: string[];
  statut: "a_envoyer" | "demandee" | "manquante" | "recue";
  fichiers: { id: string; nom_fichier: string; taille: number; sha256: string }[];
  client?: string;
  exercice?: number;
}
export const PIECE_BADGE = { a_envoyer: "bg-slate-100 text-slate-700", demandee: "bg-amber-50 text-amber-800", manquante: "bg-red-50 text-red-800", recue: "bg-emerald-50 text-emerald-800" };

export function PieceFiles({ piece }: { piece: Piece }) {
  return (
    <>
      {piece.fichiers.map((f) => (
        <button key={f.id} type="button" className="mr-2 underline" onClick={() => void download(`/client-files/${f.id}/content`, undefined, f.nom_fichier)}>{f.nom_fichier}</button>
      ))}
    </>
  );
}

/** Pièces demandées au client pour une clôture (RCO-04). */
export default function PiecesPanel({ closingId, exercice }: { closingId: string; exercice: number }) {
  const { t } = useTranslation();
  const [data, setData] = useState<{ pieces: Piece[]; totaux: Record<string, number> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [f, setF] = useState({ libelle: "", date_limite: "" });
  const url = `/closings/${closingId}/pieces`;
  const load = useCallback(() => api<{ pieces: Piece[]; totaux: Record<string, number> }>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const add = (e: FormEvent) => {
    e.preventDefault();
    void run(() => post(url, { ...f, categorie: "autre" })).then(() => setF({ libelle: "", date_limite: f.date_limite }));
  };
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  return (
    <section className="carte space-y-3" aria-labelledby={`pieces-${closingId}`}>
      <h2 id={`pieces-${closingId}`} className="text-base font-semibold">{t("pieces.titre", { exercice })}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <ul className="flex flex-wrap gap-2 text-xs">
        {Object.entries(data.totaux).map(([k, n]) => <li key={k} className={`rounded px-2 py-0.5 ${PIECE_BADGE[k as Piece["statut"]]}`}>{t(`pieces.statuts.${k}`)} : {n}</li>)}
      </ul>
      {data.pieces.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600">
            <tr>{["piece", "limite", "statut", "fichiers"].map((k) => <th key={k} scope="col" className="py-1 pr-3">{t(`pieces.${k}`)}</th>)}<th /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.pieces.map((p) => (
              <tr key={p.id}>
                <th scope="row" className="py-1 pr-3 font-normal">{p.libelle}{p.commentaire && <span className="block text-xs text-slate-500">{p.commentaire}</span>}</th>
                <td className="py-1 pr-3">{formatDate(p.date_limite)}</td>
                <td className="py-1 pr-3">
                  <span className={`rounded px-2 py-0.5 text-xs ${PIECE_BADGE[p.statut]}`}>{t(`pieces.statuts.${p.statut}`)}</span>
                  {p.relances.length > 0 && <span className="ml-1 text-xs text-slate-500">{t("pieces.relancee", { count: p.relances.length })}</span>}
                </td>
                <td className="py-1 pr-3"><PieceFiles piece={p} /></td>
                <td className="py-1 text-right">
                  {p.statut === "recue" ? (
                    <button type="button" className="underline" onClick={() => {
                      const motif = window.prompt(t("pieces.motif"));
                      if (motif) void run(() => patch(`/pieces/${p.id}`, { recue: false, commentaire: motif }));
                    }}>{t("pieces.rouvrir")}</button>
                  ) : (
                    <>
                      <button type="button" className="mr-2 underline" onClick={() => void run(() => patch(`/pieces/${p.id}`, { recue: true }))}>{t("pieces.recueHorsPortail")}</button>
                      <button type="button" className="underline" onClick={() => void run(() => del(`/pieces/${p.id}`))}>{t("pieces.retirer")}</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <div className="min-w-64 flex-1">
          <label htmlFor={`pc-lib-${closingId}`} className="etiquette">{t("pieces.piece")}</label>
          <input id={`pc-lib-${closingId}`} className="champ" required value={f.libelle} onChange={(e) => setF({ ...f, libelle: e.target.value })} />
        </div>
        <div>
          <label htmlFor={`pc-lim-${closingId}`} className="etiquette">{t("pieces.limite")}</label>
          <input id={`pc-lim-${closingId}`} type="date" className="champ" required value={f.date_limite} onChange={(e) => setF({ ...f, date_limite: e.target.value })} />
        </div>
        <button type="submit" className="btn-secondaire">{t("pieces.ajouter")}</button>
        <button type="button" className="btn-secondaire" disabled={!f.date_limite} onClick={() => void run(() => post(`${url}/standard`, { date_limite: f.date_limite }))}>{t("pieces.listeType")}</button>
        <button type="button" className="btn-primaire" disabled={!data.totaux.a_envoyer} onClick={() => void run(() => post(`${url}/send`))}>{t("pieces.envoyer")}</button>
        <button type="button" className="btn-secondaire" disabled={!data.totaux.demandee && !data.totaux.manquante} onClick={() => void run(() => post(`${url}/remind`))}>{t("pieces.relancer")}</button>
      </form>
    </section>
  );
}
