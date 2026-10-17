import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, patch } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { can } from "../lib/permissions";
import type { Criticality, Finding, Matrix, WorkpaperSummary } from "../api/types";
import Alert from "../components/Alert";
import CriticalityBadge from "../components/finding/CriticalityBadge";
import ActionPlansPanel from "../components/finding/ActionPlansPanel";
import ContradictoryPanel from "../components/finding/ContradictoryPanel";
import EvidencePanel from "../components/finding/EvidencePanel";
import PlanEvidence from "../components/finding/PlanEvidence";
import PlanPostponements from "../components/finding/PlanPostponements";
import { CRITICITES } from "../components/mission/FindingsTab";

const VOLETS = ["critere", "constat", "cause", "consequence", "recommandation"] as const;

/** Fiche constat (CON-01, CON-02) et sa vie : preuves, réponse de l'audité, plans d'action. */
export default function FindingPage() {
  const { t } = useTranslation();
  const { id, fid } = useParams();
  const { user } = useAuth();
  const [finding, setFinding] = useState<Finding | null>(null);
  const [form, setForm] = useState<Partial<Finding>>({});
  const [matrix, setMatrix] = useState<Matrix | null>(null);
  const [papers, setPapers] = useState<WorkpaperSummary[]>([]);
  const [message, setMessage] = useState<{ kind: "succes" | "erreur"; text: string } | null>(null);

  const load = useCallback(async () => {
    const f = await api<Finding>(`/findings/${fid}`);
    setFinding(f);
    setForm(f);
  }, [fid]);
  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
    api<Matrix>(`/engagements/${id}/matrix`).then(setMatrix).catch(() => setMatrix(null));
    api<WorkpaperSummary[]>(`/engagements/${id}/workpapers`).then(setPapers).catch(() => setPapers([]));
  }, [load, id]);

  if (!finding) return message ? <Alert kind="erreur">{message.text}</Alert> : <p>{t("commun.chargement")}</p>;
  const ro = !finding.peut_modifier;
  const set = (patchValue: Partial<Finding>) => setForm((f) => ({ ...f, ...patchValue }));

  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const body = {
        titre: form.titre,
        ...Object.fromEntries(VOLETS.map((k) => [k, form[k] || null])),
        criticite: form.criticite,
        risk_id: form.risk_id || null,
        control_id: form.control_id || null,
        workpaper_ids: form.workpaper_ids ?? [],
      };
      const f = await patch<Finding>(`/findings/${finding.id}`, body);
      setFinding(f);
      setForm(f);
      setMessage({ kind: "succes", text: t("constats.enregistre") });
    } catch (err) {
      setMessage({ kind: "erreur", text: (err as Error).message });
    }
  };

  return (
    <div className="space-y-4">
      <Link to={`/missions/${id}?onglet=constats`} className="text-sm text-marque-700 underline">{t("constats.retour")}</Link>
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">{finding.reference} · {finding.titre}</h1>
        <CriticalityBadge value={finding.criticite} />
        <span className="text-sm text-slate-600">{t(`constats.statuts.${finding.statut}`)}</span>
      </header>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <form onSubmit={save} className="carte space-y-3">
        <div>
          <label htmlFor="f-titre" className="etiquette">{t("constats.col.titre")}</label>
          <input id="f-titre" className="champ" required maxLength={300} disabled={ro} value={form.titre ?? ""} onChange={(e) => set({ titre: e.target.value })} />
        </div>
        {VOLETS.map((k) => (
          <div key={k}>
            <label htmlFor={`f-${k}`} className="etiquette">{t(`constats.volets.${k}`)}</label>
            <p id={`f-${k}-aide`} className="text-xs text-slate-500">{t(`constats.aides.${k}`)}</p>
            <textarea id={`f-${k}`} className="champ" rows={3} disabled={ro} aria-describedby={`f-${k}-aide`}
              value={(form[k] as string | null) ?? ""} onChange={(e) => set({ [k]: e.target.value })} />
          </div>
        ))}
        <div className="grid gap-3 md:grid-cols-3">
          <div>
            <label htmlFor="f-crit" className="etiquette">{t("constats.criticite")}</label>
            <select id="f-crit" className="champ" disabled={ro} value={form.criticite} onChange={(e) => set({ criticite: e.target.value as Criticality })}>
              {CRITICITES.map((c) => <option key={c} value={c}>{t(`constats.criticites.${c}`)}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="f-risk" className="etiquette">{t("constats.risque")}</label>
            <select id="f-risk" className="champ" disabled={ro} value={form.risk_id ?? ""} onChange={(e) => set({ risk_id: e.target.value || null })}>
              <option value="">—</option>
              {matrix?.risques.map((r) => <option key={r.id} value={r.id}>{r.libelle}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="f-ctrl" className="etiquette">{t("constats.controle")}</label>
            <select id="f-ctrl" className="champ" disabled={ro} value={form.control_id ?? ""} onChange={(e) => set({ control_id: e.target.value || null })}>
              <option value="">—</option>
              {matrix?.controles.map((c) => <option key={c.id} value={c.id}>{c.libelle}</option>)}
            </select>
          </div>
        </div>
        <fieldset>
          <legend className="etiquette">{t("constats.papiersSources")}</legend>
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {papers.map((p) => (
              <label key={p.id} className="flex items-center gap-1 text-sm">
                <input type="checkbox" disabled={ro} checked={(form.workpaper_ids ?? []).includes(p.id)}
                  onChange={(e) => set({ workpaper_ids: e.target.checked ? [...(form.workpaper_ids ?? []), p.id] : (form.workpaper_ids ?? []).filter((x) => x !== p.id) })} />
                {p.reference} · {p.titre}
              </label>
            ))}
          </div>
        </fieldset>
        {!ro && <button type="submit" className="btn-primaire">{t("commun.enregistrer")}</button>}
      </form>
      <ContradictoryPanel finding={finding} onChange={(f) => { setFinding(f); setForm(f); }}
        canSend={finding.peut_modifier} canValidate={can(user?.permissions, "findings:validate")} />
      <EvidencePanel findingId={finding.id} missionId={finding.engagement_id} papers={papers}
        editable={finding.peut_modifier} />
      <ActionPlansPanel findingId={finding.id} canCreate={finding.peut_modifier || (finding.statut === "valide" && can(user?.permissions, "findings:write"))}
        extra={(plan, reload) => (
          <>
            <PlanEvidence plan={plan} canUpload={can(user?.permissions, "findings:write")} canReject={can(user?.permissions, "findings:write")} onChange={reload} />
            <PlanPostponements plan={plan} canRequest={can(user?.permissions, "findings:write")} canDecide={can(user?.permissions, "findings:validate")} onChange={reload} />
          </>
        )} />
    </div>
  );
}
