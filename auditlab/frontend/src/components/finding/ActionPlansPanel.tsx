import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, post } from "../../api/client";
import type { ActionPlan, Auditee } from "../../api/types";
import { formatDate } from "../../lib/format";
import Alert from "../Alert";

const STATUS_COLORS: Record<ActionPlan["statut"], string> = {
  a_lancer: "bg-slate-100 text-slate-700",
  en_cours: "bg-blue-100 text-blue-800",
  realise: "bg-amber-100 text-amber-800",
  verifie: "bg-emerald-100 text-emerald-800",
  risque_accepte: "bg-purple-100 text-purple-800",
};

export function PlanStatusBadge({ plan }: { plan: ActionPlan }) {
  const { t } = useTranslation();
  return (
    <span className="inline-flex gap-1">
      <span className={`rounded px-2 py-0.5 text-xs font-semibold ${STATUS_COLORS[plan.statut]}`}>{t(`plans.statuts.${plan.statut}`)}</span>
      {plan.en_retard && <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800">{t("plans.retard")}</span>}
    </span>
  );
}

/** Plans d'action d'un constat (CON-05) ; `extra` ajoute des actions par plan (justificatifs, reports). */
export default function ActionPlansPanel({ findingId, canCreate, extra }: {
  findingId: string;
  canCreate: boolean;
  extra?: (plan: ActionPlan, reload: () => void) => ReactNode;
}) {
  const { t } = useTranslation();
  const [plans, setPlans] = useState<ActionPlan[]>([]);
  const [auditees, setAuditees] = useState<Auditee[]>([]);
  const [form, setForm] = useState({ description: "", responsable_id: "", responsable_nom: "", echeance: "" });
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<ActionPlan[]>(`/findings/${findingId}/action-plans`).then(setPlans), [findingId]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
    if (canCreate) api<Auditee[]>("/auditees").then(setAuditees).catch(() => setAuditees([]));
  }, [load, canCreate]);

  const move = async (plan: ActionPlan, statut: string) => {
    setError(null);
    let commentaire: string | null = null;
    if (statut === "risque_accepte" || statut === "realise") {
      commentaire = window.prompt(t(statut === "risque_accepte" ? "plans.justification" : "plans.commentaireRealise"));
      if (statut === "risque_accepte" && !commentaire) return;
    }
    try {
      await post(`/action-plans/${plan.id}/status`, { statut, commentaire });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const create = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await post(`/findings/${findingId}/action-plans`, {
        description: form.description,
        responsable_id: form.responsable_id || null,
        responsable_nom: form.responsable_nom || null,
        echeance: form.echeance,
      });
      setForm({ description: "", responsable_id: "", responsable_nom: "", echeance: "" });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <section className="carte space-y-3" aria-labelledby="plans-titre">
      <h2 id="plans-titre" className="text-base font-semibold">{t("plans.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {plans.length === 0 && <p className="text-sm text-slate-600">{t("plans.aucun")}</p>}
      <ul className="divide-y divide-slate-100">
        {plans.map((p) => (
          <li key={p.id} className="space-y-1 py-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <PlanStatusBadge plan={p} />
              <span className="font-medium">{p.description}</span>
              {p.propose_par_audite && <span className="text-xs text-slate-500">({t("plans.proposeAudite")})</span>}
            </div>
            <p className="text-slate-600">
              {t("plans.responsable")} : {p.responsable ?? "—"} · {t("plans.echeance")} : {formatDate(p.echeance)}
              {p.commentaire && ` · ${p.commentaire}`}
            </p>
            {p.relances.length > 0 && (
              <p className="text-xs text-slate-500">
                {t("plans.relances")} : {p.relances.map((r) => `${t(`plans.typesRelance.${r.type}`)} (${formatDate(r.date)})`).join(", ")}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {p.transitions.map((s) => (
                <button key={s} type="button" className="btn-secondaire py-1 text-xs" onClick={() => move(p, s)}>
                  {t(`plans.actions.${s}`)}
                </button>
              ))}
            </div>
            {extra?.(p, () => void load())}
          </li>
        ))}
      </ul>
      {canCreate && (
        <form onSubmit={create} className="grid gap-2 border-t border-slate-100 pt-2 md:grid-cols-4">
          <div className="md:col-span-4">
            <label htmlFor="pl-desc" className="etiquette">{t("plans.description")}</label>
            <textarea id="pl-desc" className="champ" rows={2} required value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div>
            <label htmlFor="pl-resp" className="etiquette">{t("plans.responsable")}</label>
            <select id="pl-resp" className="champ" value={form.responsable_id} onChange={(e) => setForm({ ...form, responsable_id: e.target.value })}>
              <option value="">—</option>
              {auditees.map((a) => <option key={a.id} value={a.id}>{a.nom}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="pl-resp-nom" className="etiquette">{t("plans.responsableNom")}</label>
            <input id="pl-resp-nom" className="champ" value={form.responsable_nom} onChange={(e) => setForm({ ...form, responsable_nom: e.target.value })} />
          </div>
          <div>
            <label htmlFor="pl-ech" className="etiquette">{t("plans.echeance")}</label>
            <input id="pl-ech" type="date" className="champ" required value={form.echeance} onChange={(e) => setForm({ ...form, echeance: e.target.value })} />
          </div>
          <div className="flex items-end">
            <button type="submit" className="btn-primaire">{t("plans.ajouter")}</button>
          </div>
        </form>
      )}
    </section>
  );
}
