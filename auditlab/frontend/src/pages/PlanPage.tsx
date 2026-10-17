import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, patch, post } from "../api/client";
import type { AuditableEntity, Plan, PlanItem, PlanSummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import PlanComparison from "../components/PlanComparison";
import PlanItemForm from "../components/PlanItemForm";
import type { ItemDraft } from "../components/PlanItemForm";
import { formatDate, formatDateHeure, formatNombre } from "../lib/format";
import { can, PERM } from "../lib/permissions";
import { scoreClass } from "../lib/risk";

export const STATUS_CLASSES: Record<string, string> = {
  brouillon: "bg-slate-200 text-slate-800",
  valide: "bg-green-100 text-green-900",
  remplace: "bg-amber-100 text-amber-900",
};

type ItemMode = { kind: "none" } | { kind: "add" } | { kind: "edit"; item: PlanItem };

export default function PlanPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canManage = can(user?.permissions, PERM.PLAN_MANAGE);
  const canValidate = can(user?.permissions, PERM.PLAN_VALIDATE);
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const [planId, setPlanId] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [entities, setEntities] = useState<AuditableEntity[]>([]);
  const [newYear, setNewYear] = useState(new Date().getFullYear() + 1);
  const [itemMode, setItemMode] = useState<ItemMode>({ kind: "none" });
  const [previous, setPrevious] = useState<Plan | null>(null);
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(
    null,
  );

  const loadPlans = useCallback(async () => {
    const list = await api<PlanSummary[]>("/plans");
    setPlans(list);
    setPlanId((current) => current ?? list[0]?.id ?? null);
  }, []);

  const loadPlan = useCallback(async (id: string) => {
    setPlan(await api<Plan>(`/plans/${id}`));
  }, []);

  useEffect(() => {
    Promise.all([loadPlans(), api<AuditableEntity[]>("/universe/entities").then(setEntities)]).catch(
      (e: Error) => setMessage({ kind: "erreur", text: e.message }),
    );
  }, [loadPlans]);

  useEffect(() => {
    setItemMode({ kind: "none" });
    setPrevious(null);
    if (planId) loadPlan(planId).catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
    else setPlan(null);
  }, [planId, loadPlan]);

  const run = async (action: () => Promise<unknown>, success = t("plan.enregistre")) => {
    setMessage(null);
    try {
      await action();
      setMessage({ kind: "succes", text: success });
      await loadPlans();
      if (planId) await loadPlan(planId);
      return true;
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
      return false;
    }
  };

  const editable = !!plan && plan.statut === "brouillon" && canManage;
  const candidates = useMemo(() => {
    const planned = new Set(plan?.items.map((i) => i.entity_id));
    return entities
      .filter((e) => !planned.has(e.id))
      .sort((a, b) => (b.score_risque ?? -1) - (a.score_risque ?? -1) || a.nom.localeCompare(b.nom, "fr"));
  }, [entities, plan]);

  const onCreatePlan = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const created = await post<Plan>("/plans", { annee: newYear });
      setPlanId(created.id);
      await loadPlans();
    } catch (err) {
      setMessage({ kind: "erreur", text: (err as Error).message });
    }
  };

  const onSubmitItem = async (d: ItemDraft) => {
    if (!plan) return;
    const payload = {
      titre: d.titre || null,
      budget_jours: d.budget_jours,
      periode_debut: d.periode_debut,
      periode_fin: d.periode_fin,
      justification: d.justification || null,
    };
    const ok =
      itemMode.kind === "edit"
        ? await run(() => patch(`/plans/${plan.id}/items/${itemMode.item.id}`, payload))
        : await run(() => post(`/plans/${plan.id}/items`, { ...payload, entity_id: d.entity_id }));
    if (ok) setItemMode({ kind: "none" });
  };

  const onRemove = (item: PlanItem) => {
    if (plan && window.confirm(t("plan.confirmerRetrait", { titre: item.titre }))) {
      void run(() => del(`/plans/${plan.id}/items/${item.id}`));
    }
  };

  const years = [...new Set(plans.map((p) => p.annee))];
  const versions = plan ? plans.filter((p) => p.annee === plan.annee) : [];
  const isLatest = !!plan && versions[0]?.id === plan.id;

  const onValidate = () => {
    if (plan && window.confirm(t("plan.confirmerValidation", { version: plan.version, annee: plan.annee }))) {
      void run(() => post(`/plans/${plan.id}/validate`), t("plan.valide"));
    }
  };

  const onNewVersion = async () => {
    if (!plan) return;
    setMessage(null);
    try {
      const created = await post<Plan>(`/plans/${plan.id}/new-version`);
      await loadPlans();
      setPlanId(created.id);
      setMessage({
        kind: "succes",
        text: t("plan.versionCreee", { version: created.version, precedente: plan.version }),
      });
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
    }
  };

  const toggleComparison = async () => {
    if (previous) return setPrevious(null);
    if (plan?.version_precedente_id) setPrevious(await api<Plan>(`/plans/${plan.version_precedente_id}`));
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-2xl font-semibold">{t("plan.titre")}</h1>
        {canManage && (
          <form onSubmit={onCreatePlan} className="flex items-end gap-2">
            <div>
              <label htmlFor="new-year" className="etiquette">{t("plan.annee")}</label>
              <input id="new-year" type="number" min={2000} max={2100} className="champ w-28"
                value={newYear} onChange={(e) => setNewYear(Number(e.target.value))} />
            </div>
            <button type="submit" className="btn-primaire">{t("plan.creer", { annee: newYear })}</button>
          </form>
        )}
      </header>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      {plans.length === 0 ? (
        <p className="carte text-sm text-slate-600">{t("plan.aucun")}</p>
      ) : (
        <nav aria-label={t("plan.annee")} className="flex flex-wrap gap-2">
          {years.map((y) => {
            const latest = plans.find((p) => p.annee === y)!;
            const active = plan?.annee === y;
            return (
              <button key={y} type="button" aria-pressed={active}
                className={active ? "btn-primaire" : "btn-secondaire"}
                onClick={() => setPlanId(latest.id)}>
                {y}
              </button>
            );
          })}
        </nav>
      )}

      {plan && (
        <section className="carte space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold">
                {t("plan.titre")} {plan.annee}{" "}
                <span className="text-base font-normal text-slate-600">
                  · {t("plan.version", { version: plan.version })}
                </span>{" "}
                <span className={`ml-1 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[plan.statut]}`}>
                  {t(`plan.statuts.${plan.statut}`)}
                </span>
              </h2>
              {plan.commentaire && <p className="mt-1 text-sm text-slate-600">{plan.commentaire}</p>}
              {plan.valide_le && (
                <p className="mt-1 text-sm text-slate-600">
                  {t("plan.validePar", { nom: plan.valide_par_nom ?? "", date: formatDateHeure(plan.valide_le) })}
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {canValidate && plan.statut === "brouillon" && (
                <button type="button" className="btn-primaire" onClick={onValidate}
                  disabled={plan.items.length === 0}>
                  {t("plan.valider")}
                </button>
              )}
              {canManage && isLatest && plan.statut !== "brouillon" && (
                <button type="button" className="btn-secondaire" onClick={onNewVersion}>
                  {t("plan.nouvelleVersion")}
                </button>
              )}
              {plan.version_precedente_id && (
                <button type="button" className="btn-secondaire" onClick={() => void toggleComparison()}
                  aria-pressed={!!previous}>
                  {previous ? t("plan.masquerComparaison") : t("plan.comparer", { version: plan.version - 1 })}
                </button>
              )}
            </div>
          </div>

          {versions.length > 1 && (
            <nav aria-label={t("plan.versions")} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-slate-600">{t("plan.versions")} :</span>
              {versions.map((v) => (
                <button key={v.id} type="button" aria-current={v.id === plan.id ? "page" : undefined}
                  onClick={() => setPlanId(v.id)}
                  className={`rounded-full px-3 py-1 ${v.id === plan.id ? "bg-marque-600 text-white" : STATUS_CLASSES[v.statut]}`}>
                  v{v.version} · {t(`plan.statuts.${v.statut}`)}
                </button>
              ))}
            </nav>
          )}

          {previous && <PlanComparison previous={previous} current={plan} />}

          <Charge plan={plan} editable={editable}
            onCapacity={(v) => run(() => patch(`/plans/${plan.id}`, { capacite_jours: v }))} />

          {plan.statut !== "brouillon" && canManage && (
            <Alert kind="info">{t("plan.lectureSeule")}</Alert>
          )}

          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold">{t("plan.missions", { count: plan.items.length })}</h3>
            {editable && itemMode.kind === "none" && (
              <button type="button" className="btn-secondaire" onClick={() => setItemMode({ kind: "add" })}>
                {t("plan.ajouter")}
              </button>
            )}
          </div>
          {editable && itemMode.kind !== "none" && (
            <PlanItemForm annee={plan.annee} item={itemMode.kind === "edit" ? itemMode.item : null}
              candidates={candidates} onSubmit={onSubmitItem} onCancel={() => setItemMode({ kind: "none" })} />
          )}
          {plan.items.length === 0 ? (
            <p className="text-sm text-slate-600">{t("plan.aucuneMission")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-slate-600">
                  <tr>
                    <th scope="col" className="py-2 pr-3">{t("plan.colTitre")}</th>
                    <th scope="col" className="pr-3">{t("plan.colEntite")}</th>
                    <th scope="col" className="pr-3">{t("plan.colScore")}</th>
                    <th scope="col" className="pr-3 text-right">{t("plan.colBudget")}</th>
                    <th scope="col" className="pr-3">{t("plan.colPeriode")}</th>
                    <th scope="col" className="pr-3">{t("plan.colJustification")}</th>
                    {editable && <th scope="col"><span className="sr-only">{t("utilisateurs.actions")}</span></th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {plan.items.map((i) => (
                    <tr key={i.id}>
                      <td className="py-2 pr-3 font-medium">{i.titre}</td>
                      <td className="pr-3">{i.entity_nom}</td>
                      <td className="pr-3">
                        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${scoreClass(i.score_risque)}`}>
                          {i.score_risque?.toLocaleString("fr-FR") ?? "—"}
                        </span>
                      </td>
                      <td className="pr-3 text-right">{formatNombre(i.budget_jours)}</td>
                      <td className="pr-3">
                        {t("plan.du", { debut: formatDate(i.periode_debut), fin: formatDate(i.periode_fin) })}
                      </td>
                      <td className="pr-3 text-slate-600">{i.justification}</td>
                      {editable && (
                        <td className="whitespace-nowrap">
                          <button type="button" className="mr-3 text-marque-700 underline"
                            onClick={() => setItemMode({ kind: "edit", item: i })}>
                            {t("commun.modifier")}
                          </button>
                          <button type="button" className="text-red-800 underline" onClick={() => onRemove(i)}>
                            {t("plan.retirer")}
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function Charge({
  plan,
  editable,
  onCapacity,
}: {
  plan: Plan;
  editable: boolean;
  onCapacity: (v: number | null) => void;
}) {
  const { t } = useTranslation();
  const cap = plan.capacite_jours;
  const ratio = cap ? Math.min(plan.total_jours / cap, 1) : 0;
  const over = cap !== null && plan.total_jours > cap;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-4">
        <p className="text-sm">
          {cap
            ? t("plan.charge", { total: formatNombre(plan.total_jours), capacite: formatNombre(cap) })
            : t("plan.chargeSansCapacite", { total: formatNombre(plan.total_jours) })}
        </p>
        {editable && (
          <div className="flex items-end gap-2">
            <label htmlFor="capacite" className="etiquette">{t("plan.capacite")}</label>
            <input id="capacite" type="number" min={1} className="champ mt-0 w-28" defaultValue={cap ?? ""}
              key={plan.id + String(cap)}
              onBlur={(e) => {
                const v = e.target.value ? Number(e.target.value) : null;
                if (v !== cap && (v === null || v > 0)) onCapacity(v);
              }} />
          </div>
        )}
      </div>
      {cap !== null && (
        <div className="h-2 w-full overflow-hidden rounded bg-slate-200" aria-hidden>
          <div className={`h-full ${over ? "bg-red-600" : "bg-marque-600"}`} style={{ width: `${ratio * 100}%` }} />
        </div>
      )}
      {over && (
        <p role="status" className="text-sm font-medium text-red-800">
          {t("plan.depassement", { ecart: formatNombre(plan.total_jours - (cap ?? 0)) })}
        </p>
      )}
    </div>
  );
}
