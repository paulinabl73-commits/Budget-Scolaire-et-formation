import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, put } from "../../api/client";
import type { Schedule, ScriptInfo } from "../../api/scripts";
import { formatDateHeure } from "../../lib/format";
import Alert from "../Alert";

const OPERATEURS = [">", ">=", "<", "<=", "!="] as const;

/** Planification du script pour l'audit en continu et seuil d'alerte (DAT-29). */
export default function SchedulePanel({
  script,
  canEdit,
  onChange,
}: {
  script: ScriptInfo;
  canEdit: boolean;
  onChange: (s: ScriptInfo) => void;
}) {
  const { t } = useTranslation();
  const plan = script.planification;
  const [form, setForm] = useState({
    frequence: plan?.frequence ?? "quotidienne",
    jour: String(plan?.jour ?? 1),
    heure: String(plan?.heure ?? 6),
    indicateur: plan?.alerte?.indicateur ?? "",
    operateur: plan?.alerte?.operateur ?? ">",
    seuil: String(plan?.alerte?.seuil ?? 0),
  });
  const [error, setError] = useState<string | null>(null);
  const url = `/scripts/${script.id}/schedule`;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const body: Schedule = {
      frequence: form.frequence as Schedule["frequence"],
      jour: Number(form.jour),
      heure: Number(form.heure),
      alerte: form.indicateur
        ? {
            indicateur: form.indicateur,
            operateur: form.operateur as NonNullable<
              Schedule["alerte"]
            >["operateur"],
            seuil: Number(form.seuil.replace(",", ".")),
          }
        : null,
    };
    try {
      onChange(await put<ScriptInfo>(url, body));
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const remove = async () => {
    try {
      onChange(await api<ScriptInfo>(url, { method: "DELETE" }));
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: e.target.value });
  return (
    <section className="carte space-y-3" aria-labelledby="script-planification">
      <h2 id="script-planification" className="text-base font-semibold">
        {t("planificationScript.titre")}
      </h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <p className="text-sm">
        {plan && script.prochaine_execution
          ? t("planificationScript.active", {
              frequence: t(`planificationScript.frequences.${plan.frequence}`),
              le: formatDateHeure(script.prochaine_execution),
            })
          : t("planificationScript.inactive")}
      </p>
      {canEdit && (
        <form
          onSubmit={(e) => void submit(e)}
          className="grid gap-2 md:grid-cols-6"
        >
          <label className="etiquette md:col-span-2">
            {t("planificationScript.frequence")}
            <select
              className="champ"
              value={form.frequence}
              onChange={set("frequence")}
            >
              <option value="quotidienne">
                {t("planificationScript.frequences.quotidienne")}
              </option>
              <option value="mensuelle">
                {t("planificationScript.frequences.mensuelle")}
              </option>
            </select>
          </label>
          {form.frequence === "mensuelle" && (
            <label className="etiquette">
              {t("planificationScript.jour")}
              <input
                className="champ"
                type="number"
                min={1}
                max={28}
                value={form.jour}
                onChange={set("jour")}
              />
            </label>
          )}
          <label className="etiquette">
            {t("planificationScript.heure")}
            <input
              className="champ"
              type="number"
              min={0}
              max={23}
              value={form.heure}
              onChange={set("heure")}
            />
          </label>
          <label className="etiquette md:col-span-2">
            {t("planificationScript.indicateur")}
            <input
              className="champ"
              value={form.indicateur}
              onChange={set("indicateur")}
            />
          </label>
          <label className="etiquette">
            {t("planificationScript.operateur")}
            <select
              className="champ"
              value={form.operateur}
              onChange={set("operateur")}
            >
              {OPERATEURS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
          <label className="etiquette">
            {t("planificationScript.seuil")}
            <input
              className="champ"
              inputMode="decimal"
              value={form.seuil}
              onChange={set("seuil")}
            />
          </label>
          <div className="flex gap-2 md:col-span-6">
            <button type="submit" className="btn-primaire">
              {t("planificationScript.enregistrer")}
            </button>
            {plan && (
              <button
                type="button"
                className="underline"
                onClick={() => void remove()}
              >
                {t("planificationScript.retirer")}
              </button>
            )}
          </div>
        </form>
      )}
      <p className="text-xs text-slate-600">{t("planificationScript.aide")}</p>
    </section>
  );
}
