import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, post } from "../../api/client";
import type { ReviewNote } from "../../api/types";
import { formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

const FIELDS = ["travaux", "conclusion", "objectif", "evaluation", "titre", "general"];
export const NOTE_BADGE: Record<string, string> = {
  ouverte: "bg-red-100 text-red-900",
  repondue: "bg-amber-100 text-amber-900",
  cloturee: "bg-green-100 text-green-900",
};

interface Props {
  workpaperId: string;
  isReviewer: boolean;
  isMember: boolean;
  selection: string;
  onChange: () => void;
}

export default function ReviewNotesPanel({ workpaperId, isReviewer, isMember, selection, onChange }: Props) {
  const { t } = useTranslation();
  const [notes, setNotes] = useState<ReviewNote[]>([]);
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ texte: "", champ: "travaux", citation: "" });
  const [replies, setReplies] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => setNotes(await api<ReviewNote[]>(`/workpapers/${workpaperId}/review-notes`)), [workpaperId]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      await load();
      onChange();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await run(() =>
      post(`/workpapers/${workpaperId}/review-notes`, { texte: f.texte, ancre: { champ: f.champ, citation: f.citation || null } }),
    );
    if (ok) {
      setAdding(false);
      setF({ texte: "", champ: "travaux", citation: "" });
    }
  };

  const open = notes.filter((n) => n.statut !== "cloturee").length;
  return (
    <section className="carte space-y-3" aria-labelledby="notes-titre">
      <div className="flex items-center justify-between">
        <h2 id="notes-titre" className="text-base font-semibold">
          {t("notes.titre")}
          {open > 0 && <span className="ml-2 rounded bg-red-100 px-2 py-0.5 text-xs text-red-900">{t("notes.ouvertes", { count: open })}</span>}
        </h2>
        {isReviewer && !adding && (
          <button type="button" className="btn-secondaire"
            onClick={() => { setF({ ...f, citation: selection }); setAdding(true); }}>
            {t("notes.nouvelle")}
          </button>
        )}
      </div>
      {error && <Alert kind="erreur">{error}</Alert>}
      {adding && (
        <form onSubmit={submit} className="space-y-2 rounded-md bg-slate-50 p-3">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label htmlFor="n-champ" className="etiquette">{t("notes.champ")}</label>
              <select id="n-champ" className="champ" value={f.champ} onChange={(e) => setF({ ...f, champ: e.target.value })}>
                {FIELDS.map((c) => <option key={c} value={c}>{t(`notes.champs.${c}`)}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <label htmlFor="n-cit" className="etiquette">{t("notes.citation")}</label>
              <input id="n-cit" className="champ" aria-describedby="n-cit-aide" value={f.citation}
                onChange={(e) => setF({ ...f, citation: e.target.value })} />
              <p id="n-cit-aide" className="mt-1 text-xs text-slate-600">{t("notes.citationAide")}</p>
            </div>
          </div>
          <div>
            <label htmlFor="n-texte" className="etiquette">{t("notes.texte")}</label>
            <textarea id="n-texte" rows={3} className="champ" required value={f.texte} onChange={(e) => setF({ ...f, texte: e.target.value })} />
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn-primaire">{t("notes.ajouter")}</button>
            <button type="button" className="btn-secondaire" onClick={() => setAdding(false)}>{t("commun.annuler")}</button>
          </div>
        </form>
      )}
      {notes.length === 0 ? (
        <p className="text-sm text-slate-600">{t("notes.aucune")}</p>
      ) : (
        <ul className="space-y-3">
          {notes.map((n) => (
            <li key={n.id} className="rounded-md border border-slate-200 p-3 text-sm">
              <div className="flex items-start justify-between gap-2">
                <p className="text-xs text-slate-600">
                  {t(`notes.champs.${n.ancre.champ}`)} · {n.auteur} · {formatDateHeure(n.created_at)}
                </p>
                <span className={`rounded px-2 py-0.5 text-xs font-medium ${NOTE_BADGE[n.statut]}`}>{t(`notes.statuts.${n.statut}`)}</span>
              </div>
              {n.ancre.citation && (
                <blockquote className="my-1 border-l-4 border-amber-300 bg-amber-50 px-2 py-1 text-xs italic">« {n.ancre.citation} »</blockquote>
              )}
              <p className="whitespace-pre-wrap">{n.texte}</p>
              {n.reponses.length > 0 && (
                <ul className="mt-2 space-y-1 border-l-2 border-slate-200 pl-3">
                  {n.reponses.map((r) => (
                    <li key={r.id}>
                      <span className="text-xs text-slate-600">{r.auteur} · {formatDateHeure(r.created_at)}</span>
                      <p className="whitespace-pre-wrap">{r.texte}</p>
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-2 flex flex-wrap items-end gap-2">
                {n.statut !== "cloturee" && (isMember || isReviewer) && (
                  <>
                    <label className="sr-only" htmlFor={`rep-${n.id}`}>{t("notes.reponse")}</label>
                    <input id={`rep-${n.id}`} className="champ mt-0 flex-1" placeholder={t("notes.reponse")}
                      value={replies[n.id] ?? ""} onChange={(e) => setReplies({ ...replies, [n.id]: e.target.value })} />
                    <button type="button" className="btn-secondaire" disabled={!replies[n.id]}
                      onClick={async () => {
                        if (await run(() => post(`/review-notes/${n.id}/replies`, { texte: replies[n.id] }))) setReplies({ ...replies, [n.id]: "" });
                      }}>
                      {t("notes.repondre")}
                    </button>
                  </>
                )}
                {isReviewer && (n.statut === "cloturee" ? (
                  <button type="button" className="text-xs text-marque-700 underline" onClick={() => run(() => post(`/review-notes/${n.id}/reopen`))}>{t("notes.rouvrir")}</button>
                ) : (
                  <button type="button" className="btn-primaire" onClick={() => run(() => post(`/review-notes/${n.id}/close`))}>{t("notes.cloturer")}</button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
