import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import type { AuditableEntity, PlanItem } from "../api/types";

export interface ItemDraft {
  entity_id: string;
  titre: string;
  budget_jours: number;
  periode_debut: string;
  periode_fin: string;
  justification: string;
}

interface Props {
  annee: number;
  item: PlanItem | null;
  candidates: AuditableEntity[];
  onSubmit: (draft: ItemDraft) => void;
  onCancel: () => void;
}

export default function PlanItemForm({ annee, item, candidates, onSubmit, onCancel }: Props) {
  const { t } = useTranslation();
  const blank: ItemDraft = {
    entity_id: "",
    titre: "",
    budget_jours: 20,
    periode_debut: `${annee}-01-01`,
    periode_fin: `${annee}-03-31`,
    justification: "",
  };
  const [d, setD] = useState<ItemDraft>(blank);
  useEffect(
    () =>
      setD(
        item
          ? {
              entity_id: item.entity_id,
              titre: item.titre,
              budget_jours: item.budget_jours,
              periode_debut: item.periode_debut,
              periode_fin: item.periode_fin,
              justification: item.justification ?? "",
            }
          : blank,
      ),
    [item, annee],
  );
  const set = <K extends keyof ItemDraft>(k: K, v: ItemDraft[K]) => setD((x) => ({ ...x, [k]: v }));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(d);
  };

  return (
    <form onSubmit={submit} className="grid grid-cols-4 gap-4 rounded-md bg-slate-50 p-4">
      <h3 className="col-span-4 text-base font-semibold">
        {item ? t("plan.modifierMission") : t("plan.ajouter")}
      </h3>
      {item ? (
        <p className="col-span-2 text-sm">
          <span className="etiquette">{t("plan.entite")}</span>
          {item.entity_nom}
        </p>
      ) : (
        <div className="col-span-2">
          <label htmlFor="pi-entite" className="etiquette">{t("plan.entite")}</label>
          <select id="pi-entite" className="champ" required value={d.entity_id}
            onChange={(e) => set("entity_id", e.target.value)}>
            <option value="">{t("plan.choisirEntite")}</option>
            {candidates.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nom}
                {c.score_risque !== null ? ` — ${c.score_risque.toLocaleString("fr-FR")}` : ""}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="col-span-2">
        <label htmlFor="pi-titre" className="etiquette">{t("plan.titreMission")}</label>
        <input id="pi-titre" className="champ" aria-describedby="pi-titre-aide" value={d.titre}
          onChange={(e) => set("titre", e.target.value)} />
        <p id="pi-titre-aide" className="mt-1 text-xs text-slate-600">{t("plan.titreAide")}</p>
      </div>
      <div>
        <label htmlFor="pi-budget" className="etiquette">{t("plan.budget")}</label>
        <input id="pi-budget" type="number" min={0.5} step={0.5} className="champ" required
          value={d.budget_jours} onChange={(e) => set("budget_jours", Number(e.target.value))} />
      </div>
      <div>
        <label htmlFor="pi-debut" className="etiquette">{t("plan.debut")}</label>
        <input id="pi-debut" type="date" className="champ" required min={`${annee}-01-01`}
          max={`${annee}-12-31`} value={d.periode_debut}
          onChange={(e) => set("periode_debut", e.target.value)} />
      </div>
      <div>
        <label htmlFor="pi-fin" className="etiquette">{t("plan.fin")}</label>
        <input id="pi-fin" type="date" className="champ" required min={d.periode_debut}
          max={`${annee}-12-31`} value={d.periode_fin}
          onChange={(e) => set("periode_fin", e.target.value)} />
      </div>
      <div>
        <label htmlFor="pi-just" className="etiquette">{t("plan.justification")}</label>
        <input id="pi-just" className="champ" value={d.justification}
          onChange={(e) => set("justification", e.target.value)} />
      </div>
      <div className="col-span-4 flex gap-3">
        <button type="submit" className="btn-primaire">{t("plan.enregistrer")}</button>
        <button type="button" className="btn-secondaire" onClick={onCancel}>
          {t("commun.annuler")}
        </button>
      </div>
    </form>
  );
}
