import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Dataset } from "../../api/types";

interface Rule {
  colonne: string;
  op: string;
  valeur: string;
}

const OPS = ["=", "<>", ">", ">=", "<", "<=", "CONTIENT", "EST VIDE", "EST NON VIDE"];

function literal(type: string, raw: string): string {
  if (type === "decimal" || type === "entier") return raw.replace(/\s/g, "").replace(",", ".");
  if (type === "date") return `#${raw}#`;
  return `'${raw.replace(/'/g, "''")}'`;
}

function column(nom: string): string {
  return /^[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]*$/.test(nom) ? nom : `[${nom}]`;
}

/** Constructeur visuel d'une condition (DAT-09) : produit une expression modifiable à la main. */
export default function ConditionBuilder({ columns, onChange }: { columns: Dataset["schema"]; onChange: (expr: string) => void }) {
  const { t } = useTranslation();
  const [rules, setRules] = useState<Rule[]>([]);
  const [joiner, setJoiner] = useState("ET");

  const emit = (next: Rule[], j = joiner) => {
    setRules(next);
    const parts = next.map((r) => {
      const type = columns.find((c) => c.nom === r.colonne)?.type ?? "texte";
      if (r.op.startsWith("EST")) return `${column(r.colonne)} ${r.op}`;
      return `${column(r.colonne)} ${r.op} ${literal(type, r.valeur)}`;
    });
    onChange(parts.join(` ${j} `));
  };

  return (
    <fieldset className="space-y-1 rounded border border-slate-200 p-2">
      <legend className="etiquette px-1">{t("constructeur.titre")}</legend>
      {rules.map((r, i) => {
        const type = columns.find((c) => c.nom === r.colonne)?.type;
        return (
          <div key={i} className="flex flex-wrap items-center gap-2">
            {i > 0 && <span className="w-8 text-xs font-semibold">{joiner}</span>}
            <select aria-label={t("constructeur.colonne")} className="champ mt-0 w-48" value={r.colonne}
              onChange={(e) => emit(rules.map((x, j) => (j === i ? { ...x, colonne: e.target.value } : x)))}>
              {columns.map((c) => <option key={c.nom} value={c.nom}>{c.nom}</option>)}
            </select>
            <select aria-label={t("constructeur.operateur")} className="champ mt-0 w-36" value={r.op}
              onChange={(e) => emit(rules.map((x, j) => (j === i ? { ...x, op: e.target.value } : x)))}>
              {OPS.map((o) => <option key={o} value={o}>{t(`constructeur.ops.${o}`)}</option>)}
            </select>
            {!r.op.startsWith("EST") && (
              <input aria-label={t("constructeur.valeur")} className="champ mt-0 w-40" type={type === "date" ? "date" : "text"}
                value={r.valeur} onChange={(e) => emit(rules.map((x, j) => (j === i ? { ...x, valeur: e.target.value } : x)))} />
            )}
            <button type="button" className="text-xs text-red-700 underline" onClick={() => emit(rules.filter((_, j) => j !== i))}>
              {t("analyses.retirer")}
            </button>
          </div>
        );
      })}
      <div className="flex items-center gap-3">
        <button type="button" className="text-sm text-marque-700 underline"
          onClick={() => emit([...rules, { colonne: columns[0]?.nom ?? "", op: "=", valeur: "" }])}>
          {t("constructeur.ajouter")}
        </button>
        {rules.length > 1 && (
          <label className="flex items-center gap-1 text-sm">
            {t("constructeur.combiner")}
            <select className="champ mt-0 w-20 py-0.5" value={joiner} onChange={(e) => { setJoiner(e.target.value); emit(rules, e.target.value); }}>
              <option value="ET">{t("constructeur.et")}</option>
              <option value="OU">{t("constructeur.ou")}</option>
            </select>
          </label>
        )}
      </div>
    </fieldset>
  );
}
