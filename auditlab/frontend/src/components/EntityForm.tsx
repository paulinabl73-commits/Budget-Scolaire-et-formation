import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import type { AuditableEntity, EntityType } from "../api/types";

const TYPES: EntityType[] = ["direction", "filiale", "processus", "systeme"];

export interface EntityDraft {
  nom: string;
  type: EntityType;
  parent_id: string | null;
  description: string;
  responsable: string;
  date_dernier_audit: string;
}

export function toDraft(e: AuditableEntity | null, parentId: string | null = null): EntityDraft {
  return {
    nom: e?.nom ?? "",
    type: e?.type ?? "processus",
    parent_id: e ? e.parent_id : parentId,
    description: e?.description ?? "",
    responsable: e?.responsable ?? "",
    date_dernier_audit: e?.date_dernier_audit ?? "",
  };
}

interface Props {
  initial: EntityDraft;
  parents: AuditableEntity[];
  readOnly: boolean;
  onSubmit: (draft: EntityDraft) => void;
  onCancel?: () => void;
}

export default function EntityForm({ initial, parents, readOnly, onSubmit, onCancel }: Props) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(initial);
  useEffect(() => setDraft(initial), [initial]);
  const set = <K extends keyof EntityDraft>(k: K, v: EntityDraft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(draft);
  };

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-4">
      <div className="col-span-2">
        <label htmlFor="e-nom" className="etiquette">{t("univers.nom")}</label>
        <input id="e-nom" className="champ" required disabled={readOnly} value={draft.nom}
          onChange={(e) => set("nom", e.target.value)} />
      </div>
      <div>
        <label htmlFor="e-type" className="etiquette">{t("univers.type")}</label>
        <select id="e-type" className="champ" disabled={readOnly} value={draft.type}
          onChange={(e) => set("type", e.target.value as EntityType)}>
          {TYPES.map((ty) => (
            <option key={ty} value={ty}>{t(`univers.types.${ty}`)}</option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="e-parent" className="etiquette">{t("univers.parent")}</label>
        <select id="e-parent" className="champ" disabled={readOnly} value={draft.parent_id ?? ""}
          onChange={(e) => set("parent_id", e.target.value || null)}>
          <option value="">{t("univers.racine")}</option>
          {parents.map((p) => (
            <option key={p.id} value={p.id}>{p.nom}</option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor="e-resp" className="etiquette">{t("univers.responsable")}</label>
        <input id="e-resp" className="champ" disabled={readOnly} value={draft.responsable}
          onChange={(e) => set("responsable", e.target.value)} />
      </div>
      <div>
        <label htmlFor="e-date" className="etiquette">{t("univers.dernierAudit")}</label>
        <input id="e-date" type="date" className="champ" disabled={readOnly}
          value={draft.date_dernier_audit}
          onChange={(e) => set("date_dernier_audit", e.target.value)} />
      </div>
      <div className="col-span-2">
        <label htmlFor="e-desc" className="etiquette">{t("univers.description")}</label>
        <textarea id="e-desc" rows={3} className="champ" disabled={readOnly}
          value={draft.description} onChange={(e) => set("description", e.target.value)} />
      </div>
      {!readOnly && (
        <div className="col-span-2 flex gap-3">
          <button type="submit" className="btn-primaire">{t("commun.enregistrer")}</button>
          {onCancel && (
            <button type="button" className="btn-secondaire" onClick={onCancel}>
              {t("commun.annuler")}
            </button>
          )}
        </div>
      )}
    </form>
  );
}

export function draftToPayload(d: EntityDraft) {
  return {
    nom: d.nom,
    type: d.type,
    parent_id: d.parent_id,
    description: d.description || null,
    responsable: d.responsable || null,
    date_dernier_audit: d.date_dernier_audit || null,
  };
}
