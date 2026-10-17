import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, patch } from "../api/client";
import type { Attachment, ControlAssessment, RichDoc, Workpaper, WorkpaperSummary } from "../api/types";
import Alert from "../components/Alert";
import AttachmentsPanel from "../components/workpaper/AttachmentsPanel";
import RichEditor from "../components/workpaper/RichEditor";
import { resolveImages, unresolveImages } from "../lib/richtext";

const EVALS: ControlAssessment[] = ["efficace", "partiellement_efficace", "inefficace"];

export default function WorkpaperPage() {
  const { t } = useTranslation();
  const { id, wpId } = useParams();
  const [wp, setWp] = useState<Workpaper | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [f, setF] = useState({ titre: "", objectif: "", conclusion: "", evaluation: "" });
  const [travaux, setTravaux] = useState<RichDoc>({ type: "doc", content: [] });
  const [siblings, setSiblings] = useState<WorkpaperSummary[]>([]);
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(null);

  const apply = (w: Workpaper, files: Attachment[]) => {
    setWp(w);
    setTravaux(resolveImages(w.travaux, Object.fromEntries(files.map((a) => [a.id, a.url]))));
    setF({
      titre: w.titre,
      objectif: w.objectif ?? "",
      conclusion: w.conclusion ?? "",
      evaluation: w.evaluation ?? "",
    });
  };

  const loadAttachments = useCallback(async () => {
    const files = await api<Attachment[]>(`/workpapers/${wpId}/attachments`);
    setAttachments(files);
    return files;
  }, [wpId]);
  const load = useCallback(async () => {
    const [w, files] = await Promise.all([api<Workpaper>(`/workpapers/${wpId}`), loadAttachments()]);
    apply(w, files);
    setSiblings((await api<WorkpaperSummary[]>(`/engagements/${w.engagement_id}/workpapers`)).filter((x) => x.id !== w.id));
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
          travaux: unresolveImages(travaux),
          conclusion: f.conclusion || null,
          evaluation: f.evaluation || null,
        }),
        attachments,
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
          <p className="etiquette mb-1">{t("papiers.travaux")}</p>
          <RichEditor value={travaux} editable={!ro} onChange={setTravaux} images={attachments}
            workpapers={siblings} missionId={wp.engagement_id} />
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
