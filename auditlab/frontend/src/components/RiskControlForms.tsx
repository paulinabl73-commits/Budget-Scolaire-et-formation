import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import type { ControlNature, ControlType, Cycle, Frequency, RiskCategory } from "../api/types";
import { CATEGORIES, CONTROL_TYPES, CYCLES, FREQUENCIES, NATURES } from "../lib/library";

export interface RiskDraft {
  libelle: string;
  description: string;
  cycle: Cycle;
  categorie: RiskCategory;
}

export interface ControlDraft {
  libelle: string;
  description: string;
  cycle: Cycle;
  type_controle: ControlType;
  nature: ControlNature;
  frequence: Frequency;
}

function Select<T extends string>({ id, label, value, options, prefix, onChange }: {
  id: string; label: string; value: T; options: T[]; prefix: string; onChange: (v: T) => void;
}) {
  const { t } = useTranslation();
  return (
    <div>
      <label htmlFor={id} className="etiquette">{label}</label>
      <select id={id} className="champ" value={value} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((o) => <option key={o} value={o}>{t(`${prefix}.${o}`)}</option>)}
      </select>
    </div>
  );
}

export function RiskForm({ idPrefix = "r", initialCycle = "achats", onSubmit, onCancel }: {
  idPrefix?: string; initialCycle?: Cycle; onSubmit: (d: RiskDraft) => void; onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [d, setD] = useState<RiskDraft>({ libelle: "", description: "", cycle: initialCycle, categorie: "operationnel" });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(d);
  };
  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3 rounded-md bg-slate-50 p-4">
      <div className="col-span-2">
        <label htmlFor={`${idPrefix}-lib`} className="etiquette">{t("bibliotheque.libelle")}</label>
        <input id={`${idPrefix}-lib`} className="champ" required value={d.libelle} onChange={(e) => setD({ ...d, libelle: e.target.value })} />
      </div>
      <Select id={`${idPrefix}-cycle`} label={t("bibliotheque.cycle")} value={d.cycle} options={CYCLES} prefix="bibliotheque.cycles" onChange={(v) => setD({ ...d, cycle: v })} />
      <Select id={`${idPrefix}-cat`} label={t("bibliotheque.categorie")} value={d.categorie} options={CATEGORIES} prefix="bibliotheque.categories" onChange={(v) => setD({ ...d, categorie: v })} />
      <div className="col-span-2">
        <label htmlFor={`${idPrefix}-desc`} className="etiquette">{t("bibliotheque.description")}</label>
        <textarea id={`${idPrefix}-desc`} rows={2} className="champ" value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} />
      </div>
      <div className="col-span-2 flex gap-2">
        <button type="submit" className="btn-primaire">{t("bibliotheque.ajouter")}</button>
        <button type="button" className="btn-secondaire" onClick={onCancel}>{t("commun.annuler")}</button>
      </div>
    </form>
  );
}

export function ControlForm({ idPrefix = "c", initialCycle = "achats", onSubmit, onCancel }: {
  idPrefix?: string; initialCycle?: Cycle; onSubmit: (d: ControlDraft) => void; onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [d, setD] = useState<ControlDraft>({
    libelle: "", description: "", cycle: initialCycle, type_controle: "preventif", nature: "manuel", frequence: "mensuel",
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(d);
  };
  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3 rounded-md bg-slate-50 p-4 md:grid-cols-4">
      <div className="col-span-2 md:col-span-4">
        <label htmlFor={`${idPrefix}-lib`} className="etiquette">{t("bibliotheque.libelle")}</label>
        <input id={`${idPrefix}-lib`} className="champ" required value={d.libelle} onChange={(e) => setD({ ...d, libelle: e.target.value })} />
      </div>
      <Select id={`${idPrefix}-cycle`} label={t("bibliotheque.cycle")} value={d.cycle} options={CYCLES} prefix="bibliotheque.cycles" onChange={(v) => setD({ ...d, cycle: v })} />
      <Select id={`${idPrefix}-type`} label={t("bibliotheque.type")} value={d.type_controle} options={CONTROL_TYPES} prefix="bibliotheque.types" onChange={(v) => setD({ ...d, type_controle: v })} />
      <Select id={`${idPrefix}-nat`} label={t("bibliotheque.nature")} value={d.nature} options={NATURES} prefix="bibliotheque.natures" onChange={(v) => setD({ ...d, nature: v })} />
      <Select id={`${idPrefix}-freq`} label={t("bibliotheque.frequence")} value={d.frequence} options={FREQUENCIES} prefix="bibliotheque.frequences" onChange={(v) => setD({ ...d, frequence: v })} />
      <div className="col-span-2 md:col-span-4">
        <label htmlFor={`${idPrefix}-desc`} className="etiquette">{t("bibliotheque.description")}</label>
        <textarea id={`${idPrefix}-desc`} rows={2} className="champ" value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} />
      </div>
      <div className="col-span-2 flex gap-2 md:col-span-4">
        <button type="submit" className="btn-primaire">{t("bibliotheque.ajouter")}</button>
        <button type="button" className="btn-secondaire" onClick={onCancel}>{t("commun.annuler")}</button>
      </div>
    </form>
  );
}

export function controlPayload(d: ControlDraft) {
  return { ...d, description: d.description || null };
}

export function riskPayload(d: RiskDraft) {
  return { ...d, description: d.description || null };
}
