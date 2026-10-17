import { useState } from "react";
import { useTranslation } from "react-i18next";

import { put } from "../../api/client";
import type { Engagement, Procedure, ProcedureStatus } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { formatDate } from "../../lib/format";

const STATUSES: ProcedureStatus[] = ["a_faire", "en_cours", "terminee"];
const BADGE: Record<ProcedureStatus, string> = {
  a_faire: "bg-slate-100 text-slate-700",
  en_cours: "bg-sky-100 text-sky-900",
  terminee: "bg-green-100 text-green-900",
};

interface Props {
  mission: Engagement;
  procedure: Procedure;
  editable: boolean;
  onRemove: () => void;
  onChanged: () => void;
  onError: (message: string) => void;
}

/** Procédure avec son affectation, son échéance et son avancement (AUD-12). */
export default function ProcedureLine({ mission, procedure: p, editable, onRemove, onChanged, onError }: Props) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [assigning, setAssigning] = useState(false);
  const [who, setWho] = useState(p.assigne_a ?? "");
  const [when, setWhen] = useState(p.echeance ?? "");
  const open = mission.statut !== "cloturee";
  const canProgress = open && (p.assigne_a === user?.id || mission.peut_gerer);
  const base = `/engagements/${mission.id}/procedures/${p.id}`;

  const call = async (action: () => Promise<unknown>) => {
    try {
      await action();
      onChanged();
    } catch (e) {
      onError((e as Error).message);
    }
  };

  return (
    <li className="space-y-1 rounded border border-slate-100 p-2">
      <div className="flex items-start justify-between gap-3 text-sm">
        <span>
          <span className="font-mono text-xs text-slate-600">{p.reference}</span> {p.description}{" "}
          <span className="text-xs text-slate-500">— {t(`programme.typesTest.${p.type_test}`)}</span>
        </span>
        {editable && (
          <button type="button" className="text-xs text-red-800 underline" onClick={onRemove}>{t("commun.supprimer")}</button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className={`rounded px-2 py-0.5 font-medium ${BADGE[p.statut]}`}>{t(`programme.statuts.${p.statut}`)}</span>
        <span>{t("programme.assigneA")} : {p.assigne_nom ?? t("programme.nonAffectee")}</span>
        {p.echeance && (
          <span className={p.en_retard ? "font-semibold text-red-800" : ""}>
            {t("programme.echeance")} : {formatDate(p.echeance)}{p.en_retard && ` (${t("programme.enRetard")})`}
          </span>
        )}
        {canProgress && (
          <label className="flex items-center gap-1">
            <span className="sr-only">{t("programme.avancement")} {p.reference}</span>
            <select className="rounded border border-slate-300 px-1 py-0.5" value={p.statut}
              onChange={(e) => call(() => put(`${base}/status`, { statut: e.target.value }))}>
              {STATUSES.map((s) => <option key={s} value={s}>{t(`programme.statuts.${s}`)}</option>)}
            </select>
          </label>
        )}
        {editable && !assigning && (
          <button type="button" className="text-marque-700 underline" onClick={() => setAssigning(true)}>
            {t("programme.affecter")}
          </button>
        )}
      </div>
      {assigning && (
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor={`as-${p.id}`} className="etiquette">{t("programme.assigneA")}</label>
            <select id={`as-${p.id}`} className="champ" value={who} onChange={(e) => setWho(e.target.value)}>
              <option value="">{t("programme.personne")}</option>
              {mission.membres.map((m) => <option key={m.user_id} value={m.user_id}>{m.nom}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor={`ec-${p.id}`} className="etiquette">{t("programme.echeance")}</label>
            <input id={`ec-${p.id}`} type="date" className="champ" min={mission.date_debut} max={mission.date_fin}
              value={when} onChange={(e) => setWhen(e.target.value)} />
          </div>
          <button type="button" className="btn-primaire"
            onClick={async () => {
              await call(() => put(`${base}/assignment`, { assigne_a: who || null, echeance: when || null }));
              setAssigning(false);
            }}>
            {t("commun.enregistrer")}
          </button>
          <button type="button" className="btn-secondaire" onClick={() => setAssigning(false)}>{t("commun.annuler")}</button>
        </div>
      )}
    </li>
  );
}
