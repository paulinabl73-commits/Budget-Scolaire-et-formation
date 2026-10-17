import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { api, post } from "../../api/client";
import type { ActionPlan, Criticality } from "../../api/types";
import Alert from "../../components/Alert";
import CriticalityBadge from "../../components/finding/CriticalityBadge";
import { PlanStatusBadge } from "../../components/finding/ActionPlansPanel";
import PlanEvidence from "../../components/finding/PlanEvidence";
import PlanPostponements from "../../components/finding/PlanPostponements";
import { formatDate } from "../../lib/format";

interface Detail {
  id: string;
  reference: string;
  titre: string;
  critere: string | null;
  constat: string | null;
  cause: string | null;
  consequence: string | null;
  recommandation: string | null;
  criticite: Criticality;
  statut: string;
  date_limite_reponse: string | null;
  reponse_position: string | null;
  reponse_commentaire: string | null;
  mission: { reference: string; titre: string };
  peut_repondre: boolean;
  plans: ActionPlan[];
}

const VOLETS = ["critere", "constat", "cause", "consequence", "recommandation"] as const;

/** Constat vu depuis le portail audité : réponse, plans, justificatifs, reports (CON-04 à CON-09). */
export default function PortalFindingPage() {
  const { t } = useTranslation();
  const { fid } = useParams();
  const [f, setF] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [position, setPosition] = useState("accord");
  const [commentaire, setCommentaire] = useState("");
  const [plans, setPlans] = useState<{ description: string; responsable_nom: string; echeance: string }[]>([]);
  const load = useCallback(() => api<Detail>(`/portal/findings/${fid}`).then(setF), [fid]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);

  if (!f) return error ? <Alert kind="erreur">{error}</Alert> : <p>{t("commun.chargement")}</p>;

  const answer = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      setF(await post<Detail>(`/portal/findings/${f.id}/response`, {
        position,
        commentaire: commentaire || null,
        plans: plans.map((p) => ({ ...p, responsable_nom: p.responsable_nom || null })),
      }));
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const move = async (plan: ActionPlan, statut: string) => {
    try {
      await post(`/action-plans/${plan.id}/status`, { statut, commentaire: null });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <Link to="/" className="text-sm text-marque-700 underline">{t("portail.retour")}</Link>
      <header className="space-y-1">
        <p className="text-sm text-slate-600">{f.mission.reference} · {f.mission.titre}</p>
        <h1 className="flex flex-wrap items-center gap-3 text-2xl font-semibold">
          {f.reference} · {f.titre} <CriticalityBadge value={f.criticite} />
        </h1>
      </header>
      {error && <Alert kind="erreur">{error}</Alert>}
      <section className="carte space-y-3">
        {VOLETS.map((k) => f[k] && (
          <div key={k}>
            <h2 className="etiquette">{t(`constats.volets.${k}`)}</h2>
            <p className="whitespace-pre-line text-sm">{f[k]}</p>
          </div>
        ))}
      </section>
      {f.peut_repondre ? (
        <form onSubmit={answer} className="carte space-y-3" aria-labelledby="reponse-titre">
          <h2 id="reponse-titre" className="text-base font-semibold">{t("portail.votreReponse", { date: formatDate(f.date_limite_reponse) })}</h2>
          <fieldset className="flex flex-wrap gap-4 text-sm">
            <legend className="etiquette">{t("portail.position")}</legend>
            {["accord", "accord_partiel", "desaccord"].map((p) => (
              <label key={p} className="flex items-center gap-1">
                <input type="radio" name="position" value={p} checked={position === p} onChange={() => setPosition(p)} />
                {t(`portail.positions.${p}`)}
              </label>
            ))}
          </fieldset>
          <div>
            <label htmlFor="rp-com" className="etiquette">{t("portail.commentaire")}</label>
            <textarea id="rp-com" className="champ" rows={4} required={position !== "accord"} value={commentaire} onChange={(e) => setCommentaire(e.target.value)} />
          </div>
          <fieldset className="space-y-2">
            <legend className="etiquette">{t("portail.plansProposes")}</legend>
            {plans.map((p, i) => (
              <div key={i} className="grid gap-2 md:grid-cols-4">
                <input aria-label={t("plans.description")} placeholder={t("plans.description")} className="champ mt-0 md:col-span-2" required value={p.description}
                  onChange={(e) => setPlans(plans.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} />
                <input aria-label={t("plans.responsableNom")} placeholder={t("portail.responsable")} className="champ mt-0" value={p.responsable_nom}
                  onChange={(e) => setPlans(plans.map((x, j) => (j === i ? { ...x, responsable_nom: e.target.value } : x)))} />
                <input aria-label={t("plans.echeance")} type="date" className="champ mt-0" required value={p.echeance}
                  onChange={(e) => setPlans(plans.map((x, j) => (j === i ? { ...x, echeance: e.target.value } : x)))} />
              </div>
            ))}
            <button type="button" className="text-sm text-marque-700 underline" onClick={() => setPlans([...plans, { description: "", responsable_nom: "", echeance: "" }])}>
              {t("portail.ajouterPlan")}
            </button>
          </fieldset>
          <button type="submit" className="btn-primaire">{t("portail.envoyerReponse")}</button>
        </form>
      ) : f.reponse_position && (
        <section className="carte text-sm">
          <h2 className="etiquette">{t("portail.reponseEnvoyee")}</h2>
          <p className="font-medium">{t(`portail.positions.${f.reponse_position}`, { defaultValue: t(`contradictoire.positions.${f.reponse_position}`) })}</p>
          {f.reponse_commentaire && <p className="whitespace-pre-line">{f.reponse_commentaire}</p>}
        </section>
      )}
      <section className="carte space-y-3" aria-labelledby="portail-plans">
        <h2 id="portail-plans" className="text-base font-semibold">{t("plans.titre")}</h2>
        {f.plans.length === 0 && <p className="text-sm text-slate-600">{t("plans.aucun")}</p>}
        <ul className="divide-y divide-slate-100">
          {f.plans.map((p) => (
            <li key={p.id} className="space-y-1 py-2 text-sm">
              <div className="flex flex-wrap items-center gap-2"><PlanStatusBadge plan={p} /> <span className="font-medium">{p.description}</span></div>
              <p className="text-slate-600">{t("plans.responsable")} : {p.responsable ?? "—"} · {t("plans.echeance")} : {formatDate(p.echeance)}{p.commentaire && ` · ${p.commentaire}`}</p>
              <div className="flex flex-wrap gap-2">
                {p.transitions.map((s) => (
                  <button key={s} type="button" className="btn-secondaire py-1 text-xs" onClick={() => move(p, s)}>{t(`plans.actions.${s}`)}</button>
                ))}
              </div>
              <PlanEvidence plan={p} canUpload canReject={false} onChange={() => void load()} />
              <PlanPostponements plan={p} canRequest canDecide={false} onChange={() => void load()} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
