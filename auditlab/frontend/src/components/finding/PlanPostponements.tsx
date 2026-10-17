import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, post } from "../../api/client";
import type { ActionPlan } from "../../api/types";
import { formatDate, formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

interface Postponement {
  id: string;
  ancienne_echeance: string;
  nouvelle_echeance: string;
  motif: string;
  statut: "demande" | "accepte" | "refuse";
  demande_par: string | null;
  demande_le: string | null;
  decide_par: string | null;
  commentaire_decision: string | null;
}

/** Reports d'échéance (CON-08) : demande, décision du chef de mission, historique. */
export default function PlanPostponements({ plan, canRequest, canDecide, onChange }: { plan: ActionPlan; canRequest: boolean; canDecide: boolean; onChange: () => void }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Postponement[]>([]);
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState("");
  const [motif, setMotif] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<Postponement[]>(`/action-plans/${plan.id}/postponements`).then(setItems), [plan.id]);
  useEffect(() => {
    load().catch(() => setItems([]));
  }, [load]);
  const closed = plan.statut === "verifie" || plan.statut === "risque_accepte";
  const pending = items.some((p) => p.statut === "demande");

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
      onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="ml-4 space-y-1 border-l-2 border-slate-100 pl-3 text-xs">
      {error && <Alert kind="erreur">{error}</Alert>}
      {items.length > 0 && (
        <ul>
          {items.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-2">
              <span>
                {t("reports.ligne", { de: formatDate(p.ancienne_echeance), a: formatDate(p.nouvelle_echeance), par: p.demande_par, le: formatDateHeure(p.demande_le) })}
                {" — "}{p.motif} · <strong>{t(`reports.statuts.${p.statut}`)}</strong>
                {p.decide_par && ` (${p.decide_par}${p.commentaire_decision ? ` : ${p.commentaire_decision}` : ""})`}
              </span>
              {canDecide && p.statut === "demande" && (
                <>
                  <button type="button" className="btn-secondaire py-0.5 text-xs" onClick={() => run(() => post(`/postponements/${p.id}/decision`, { decision: "accepte" }))}>{t("reports.accepter")}</button>
                  <button type="button" className="btn-secondaire py-0.5 text-xs"
                    onClick={() => { const c = window.prompt(t("reports.motifRefus")); if (c !== null) void run(() => post(`/postponements/${p.id}/decision`, { decision: "refuse", commentaire: c || null })); }}>
                    {t("reports.refuser")}
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {canRequest && !closed && !pending && (
        open ? (
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label htmlFor={`rp-date-${plan.id}`} className="etiquette">{t("reports.nouvelle")}</label>
              <input id={`rp-date-${plan.id}`} type="date" className="champ mt-0" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="min-w-48 flex-1">
              <label htmlFor={`rp-motif-${plan.id}`} className="etiquette">{t("reports.motif")}</label>
              <input id={`rp-motif-${plan.id}`} className="champ mt-0" value={motif} onChange={(e) => setMotif(e.target.value)} />
            </div>
            <button type="button" className="btn-primaire py-1 text-xs" disabled={!date || !motif}
              onClick={() => run(async () => { await post(`/action-plans/${plan.id}/postponements`, { nouvelle_echeance: date, motif }); setOpen(false); setMotif(""); })}>
              {t("reports.demander")}
            </button>
          </div>
        ) : (
          <button type="button" className="text-marque-700 underline" onClick={() => setOpen(true)}>{t("reports.ouvrir")}</button>
        )
      )}
    </div>
  );
}
