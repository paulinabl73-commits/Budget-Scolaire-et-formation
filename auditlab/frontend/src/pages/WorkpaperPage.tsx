import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, patch } from "../api/client";
import type { Attachment, ControlAssessment, Workpaper } from "../api/types";
import Alert from "../components/Alert";
import AttachmentsPanel from "../components/workpaper/AttachmentsPanel";
import { fromPlainText, toPlainText } from "../lib/richtext";

const EVALS: ControlAssessment[] = ["efficace", "partiellement_efficace", "inefficace"];

export default function WorkpaperPage() {
  const { t } = useTranslation();
  const { id, wpId } = useParams();
  const [wp, setWp] = useState<Workpaper | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [f, setF] = useState({ titre: "", objectif: "", travaux: "", conclusion: "", evaluation: "" });
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(null);

  const apply = (w: Workpaper) => {
    setWp(w);
    setF({
      titre: w.titre,
      objectif: w.objectif ?? "",
      travaux: toPlainText(w.travaux),
      conclusion: w.conclusion ?? "",
      evaluation: w.evaluation ?? "",
    });
  };

  const loadAttachments = useCallback(
    async () => setAttachments(await api<Attachment[]>(`/workpapers/${wpId}/attachments`)),
    [wpId],
  );
  const load = useCallback(async () => {
    apply(await api<Workpaper>(`/workpapers/${wpId}`));
    await loadAttachments();
  }, [wpId, loadAttachments]);
  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
  }, [load]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setMessage(null);
    try {
      apply(
        await patch<Workpaper>(`/workpapers/${wpId}`, {
          titre: f.titre,
          objectif: f.objectif || null,
          travaux: fromPlainText(f.travaux),
          conclusion: f.conclusion || null,
          evaluation: f.evaluation || null,
        }),
      );
      setMessage({ kind: "succes", text: t("papiers.enregistre") });
    } catch (err) {
      setMessage({ kind: "erreur", text: (err as Error).message });
    }
  };

  if (!wp) return message ? <Alert kind={message.kind}>{message.text}</Alert> : <p>{t("commun.chargement")}</p>;
  const ro = !wp.peut_modifier;
  return (
    <div className="space-y-4">
      <Link to={`/missions/${id}?onglet=papiers`} className="text-sm text-marque-700 underline">{t("papiers.retour")}</Link>
      <header>
        <p className="font-mono text-sm text-slate-600">
          {wp.reference}
          {wp.procedure_reference && ` · ${wp.procedure_reference}`} · {t("papiers.version", { version: wp.version })}
        </p>
        <h1 className="text-2xl font-semibold">{wp.titre}</h1>
      </header>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <form onSubmit={save} className="carte space-y-4">
        <div>
          <label htmlFor="w-titre" className="etiquette">{t("papiers.intitule")}</label>
          <input id="w-titre" className="champ" disabled={ro} required value={f.titre} onChange={(e) => setF({ ...f, titre: e.target.value })} />
        </div>
        <div>
          <label htmlFor="w-obj" className="etiquette">{t("papiers.objectif")}</label>
          <textarea id="w-obj" rows={2} className="champ" disabled={ro} value={f.objectif} onChange={(e) => setF({ ...f, objectif: e.target.value })} />
        </div>
        <div>
          <label htmlFor="w-trav" className="etiquette">{t("papiers.travaux")}</label>
          <textarea id="w-trav" rows={10} className="champ" disabled={ro} value={f.travaux} onChange={(e) => setF({ ...f, travaux: e.target.value })} />
        </div>
        <div>
          <label htmlFor="w-concl" className="etiquette">{t("papiers.conclusion")}</label>
          <textarea id="w-concl" rows={3} className="champ" disabled={ro} value={f.conclusion} onChange={(e) => setF({ ...f, conclusion: e.target.value })} />
        </div>
        <div className="max-w-xs">
          <label htmlFor="w-eval" className="etiquette">{t("papiers.evaluation")}</label>
          <select id="w-eval" className="champ" disabled={ro} value={f.evaluation} onChange={(e) => setF({ ...f, evaluation: e.target.value })}>
            <option value="">{t("papiers.nonEvalue")}</option>
            {EVALS.map((v) => <option key={v} value={v}>{t(`papiers.evaluations.${v}`)}</option>)}
          </select>
        </div>
        {!ro && <button type="submit" className="btn-primaire">{t("commun.enregistrer")}</button>}
      </form>
      <AttachmentsPanel workpaperId={wp.id} attachments={attachments} editable={!ro} onChange={() => void loadAttachments()} />
    </div>
  );
}
