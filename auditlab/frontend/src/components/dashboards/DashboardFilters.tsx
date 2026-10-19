import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";

export interface DashboardFilter {
  debut: string;
  fin: string;
  entity_id: string;
  criticite: string;
}

export const EMPTY_FILTER: DashboardFilter = {
  debut: "",
  fin: "",
  entity_id: "",
  criticite: "",
};

export function toQuery(f: DashboardFilter): string {
  const params = new URLSearchParams(
    Object.entries(f).filter(([, v]) => v) as [string, string][],
  );
  const q = params.toString();
  return q ? `?${q}` : "";
}

/** Filtres communs des tableaux de bord (REP-08) : période, entité, criticité. */
export default function DashboardFilters({
  value,
  onChange,
  criticite = false,
}: {
  value: DashboardFilter;
  onChange: (f: DashboardFilter) => void;
  criticite?: boolean;
}) {
  const { t } = useTranslation();
  const [entities, setEntities] = useState<{ id: string; nom: string }[]>([]);
  useEffect(() => {
    api<{ id: string; nom: string }[]>("/universe/entities").then(
      setEntities,
      () => setEntities([]),
    );
  }, []);
  const set =
    (k: keyof DashboardFilter) => (e: { target: { value: string } }) =>
      onChange({ ...value, [k]: e.target.value });
  return (
    <form
      className="carte grid gap-2 md:grid-cols-5"
      aria-label={t("tableauxDeBord.filtres")}
      onSubmit={(e) => e.preventDefault()}
    >
      <label className="etiquette">
        {t("tableauxDeBord.debut")}
        <input
          type="date"
          className="champ"
          value={value.debut}
          onChange={set("debut")}
        />
      </label>
      <label className="etiquette">
        {t("tableauxDeBord.fin")}
        <input
          type="date"
          className="champ"
          value={value.fin}
          onChange={set("fin")}
        />
      </label>
      <label className="etiquette">
        {t("tableauxDeBord.entite")}
        <select
          className="champ"
          value={value.entity_id}
          onChange={set("entity_id")}
        >
          <option value="">{t("tableauxDeBord.toutes")}</option>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>
              {e.nom}
            </option>
          ))}
        </select>
      </label>
      {criticite && (
        <label className="etiquette">
          {t("tableauxDeBord.criticite")}
          <select
            className="champ"
            value={value.criticite}
            onChange={set("criticite")}
          >
            <option value="">{t("tableauxDeBord.toutes")}</option>
            {["critique", "elevee", "moyenne", "faible"].map((c) => (
              <option key={c} value={c}>
                {t(`constats.criticites.${c}`)}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="flex items-end">
        <button
          type="button"
          className="underline"
          onClick={() => onChange(EMPTY_FILTER)}
        >
          {t("tableauxDeBord.reinitialiser")}
        </button>
      </div>
    </form>
  );
}
