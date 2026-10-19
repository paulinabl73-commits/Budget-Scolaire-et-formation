import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, post } from "../api/client";
import type { AuditableEntity, RiskAssessment, RiskCriterion } from "../api/types";
import { formatDate } from "../lib/format";
import { scoreClass, seniorityNote, today } from "../lib/risk";
import Alert from "./Alert";

interface Props {
  entity: AuditableEntity;
  canManage: boolean;
  onSaved: () => void;
}

const NOTES = [1, 2, 3, 4, 5];

export default function AssessmentPanel({ entity, canManage, onSaved }: Props) {
  const { t } = useTranslation();
  const [criteria, setCriteria] = useState<RiskCriterion[]>([]);
  const [history, setHistory] = useState<RiskAssessment[]>([]);
  const [notes, setNotes] = useState<Record<string, number>>({});
  const [dateEval, setDateEval] = useState(today());
  const [commentaire, setCommentaire] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(
    null,
  );

  const load = useCallback(async () => {
    const [c, h] = await Promise.all([
      api<RiskCriterion[]>("/risk/criteria"),
      api<RiskAssessment[]>(`/universe/entities/${entity.id}/assessments`),
    ]);
    setCriteria(c.filter((x) => x.actif));
    setHistory(h);
    // Pré-remplit avec la dernière évaluation pour faciliter une réévaluation.
    const last = h[0];
    setNotes(Object.fromEntries((last?.criteres ?? []).map((x) => [x.code, x.note])));
  }, [entity.id]);

  useEffect(() => {
    setShowForm(false);
    setMessage(null);
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
  }, [load]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const payload = Object.fromEntries(
      criteria.filter((c) => c.mode === "note").map((c) => [c.code, notes[c.code] ?? 3]),
    );
    try {
      await post(`/universe/entities/${entity.id}/assessments`, {
        notes: payload,
        date_evaluation: dateEval,
        commentaire: commentaire || null,
      });
      setMessage({ kind: "succes", text: t("evaluation.enregistree") });
      setShowForm(false);
      setCommentaire("");
      await load();
      onSaved();
    } catch (err) {
      setMessage({ kind: "erreur", text: (err as Error).message });
    }
  };

  return (
    <section aria-labelledby="eval-titre" className="space-y-4 border-t border-slate-200 pt-4">
      <div className="flex items-center justify-between">
        <h3 id="eval-titre" className="text-base font-semibold">{t("evaluation.titre")}</h3>
        {canManage && !showForm && (
          <button type="button" className="btn-secondaire" onClick={() => setShowForm(true)}>
            {t("evaluation.nouvelle")}
          </button>
        )}
      </div>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      {showForm && (
        <form onSubmit={onSubmit} className="space-y-3 rounded-md bg-slate-50 p-4">
          <p className="text-xs text-slate-600">{t("evaluation.echelle")}</p>
          {criteria.map((c) => (
            <div key={c.code} className="grid grid-cols-3 items-center gap-3">
              <label htmlFor={`note-${c.code}`} className="etiquette col-span-2">
                {c.libelle}{" "}
                <span className="text-xs font-normal text-slate-600">
                  ({t(`criteres.axes.${c.axe}`)} · {t("criteres.poids")} {c.poids})
                </span>
              </label>
              {c.mode === "anciennete" ? (
                <p id={`note-${c.code}`} className="text-sm" title={t("evaluation.autoAide")}>
                  {t("evaluation.auto", { note: seniorityNote(entity.date_dernier_audit, dateEval) })}
                </p>
              ) : (
                <select id={`note-${c.code}`} className="champ mt-0" value={notes[c.code] ?? 3}
                  onChange={(e) => setNotes({ ...notes, [c.code]: Number(e.target.value) })}>
                  {NOTES.map((n) => (
                    <option key={n} value={n}>{t(`evaluation.notes.${n}`)}</option>
                  ))}
                </select>
              )}
            </div>
          ))}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label htmlFor="eval-date" className="etiquette">{t("evaluation.date")}</label>
              <input id="eval-date" type="date" className="champ" required value={dateEval}
                onChange={(e) => setDateEval(e.target.value)} />
            </div>
            <div className="col-span-2">
              <label htmlFor="eval-com" className="etiquette">{t("evaluation.commentaire")}</label>
              <input id="eval-com" className="champ" value={commentaire}
                onChange={(e) => setCommentaire(e.target.value)} />
            </div>
          </div>
          <div className="flex gap-3">
            <button type="submit" className="btn-primaire">{t("evaluation.evaluer")}</button>
            <button type="button" className="btn-secondaire" onClick={() => setShowForm(false)}>
              {t("commun.annuler")}
            </button>
          </div>
        </form>
      )}

      <h4 className="text-sm font-medium text-slate-700">{t("evaluation.historique")}</h4>
      {history.length === 0 ? (
        <p className="text-sm text-slate-600">{t("evaluation.aucune")}</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-slate-600">
            <tr>
              <th scope="col" className="py-1">{t("evaluation.date")}</th>
              <th scope="col">{t("evaluation.score")}</th>
              <th scope="col">{t("evaluation.impact")}</th>
              <th scope="col">{t("evaluation.probabilite")}</th>
              <th scope="col">{t("evaluation.detail")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {history.map((a) => (
              <tr key={a.id}>
                <td className="py-1.5">{formatDate(a.date_evaluation)}</td>
                <td>
                  <span className={`rounded px-2 py-0.5 font-semibold ${scoreClass(a.score)}`}>
                    {a.score.toLocaleString("fr-FR")}
                  </span>
                </td>
                <td>{a.impact?.toLocaleString("fr-FR") ?? "—"}</td>
                <td>{a.probabilite?.toLocaleString("fr-FR") ?? "—"}</td>
                <td className="text-xs text-slate-600">
                  {a.criteres.map((c) => `${c.libelle} : ${c.note}`).join(" · ")}
                  {a.commentaire && <span className="block italic">{a.commentaire}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
