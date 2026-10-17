import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api, post, put } from "../../api/client";
import type { Dataset } from "../../api/types";
import Alert from "../Alert";

interface Check {
  valide: boolean;
  erreur: string | null;
  position: number | null;
  type: string | null;
  apercu: unknown[];
}

interface Field {
  nom: string;
  expression: string;
}

/** Champs calculés (DAT-06) : une vue sur la table, la source n'est jamais modifiée. */
export default function CalculatedFields({ ds, canEdit, onChanged }: { ds: Dataset; canEdit: boolean; onChanged: (d: Dataset) => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const fields = ((ds.definition.champs as Field[] | undefined) ?? []);
  const isView = ds.kind === "vue";
  const [nom, setNom] = useState("");
  const [expression, setExpression] = useState("");
  const [viewName, setViewName] = useState(`${ds.nom} (calculs)`);
  const [check, setCheck] = useState<Check | null>(null);
  const [functions, setFunctions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<string[]>("/expressions/functions").then(setFunctions).catch(() => setFunctions([]));
  }, []);

  // Contrôle à la saisie, après une courte pause.
  useEffect(() => {
    if (!expression.trim()) {
      setCheck(null);
      return;
    }
    const timer = setTimeout(() => {
      post<Check>(`/datasets/${ds.id}/expressions/validate`, { expression }).then(setCheck).catch(() => setCheck(null));
    }, 400);
    return () => clearTimeout(timer);
  }, [expression, ds.id]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const champ = { nom: nom.trim(), expression };
      if (isView) {
        onChanged(await put<Dataset>(`/datasets/${ds.id}/view`, { champs: [...fields, champ] }));
      } else {
        const view = await post<Dataset>(`/datasets/${ds.id}/views`, { nom: viewName, champs: [champ] });
        navigate(`/missions/${ds.engagement_id}/donnees/${view.id}`);
      }
      setNom("");
      setExpression("");
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const remove = async (index: number) => {
    setError(null);
    try {
      onChanged(await put<Dataset>(`/datasets/${ds.id}/view`, { champs: fields.filter((_, i) => i !== index) }));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <section className="carte space-y-3" aria-labelledby="calc-titre">
      <h2 id="calc-titre" className="text-base font-semibold">{t("calcul.titre")}</h2>
      <p className="text-sm text-slate-600">{isView ? t("calcul.aideVue") : t("calcul.aideSource")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      {fields.length > 0 && (
        <ul className="divide-y divide-slate-100 text-sm">
          {fields.map((f, i) => (
            <li key={f.nom} className="flex items-center justify-between gap-2 py-1">
              <span><strong>{f.nom}</strong> = <code className="text-xs">{f.expression}</code></span>
              {canEdit && fields.length > 1 && (
                <button type="button" className="text-xs text-red-700 underline" onClick={() => remove(i)}>
                  {t("calcul.retirer", { nom: f.nom })}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <form onSubmit={submit} className="space-y-2">
          <div className="grid gap-2 md:grid-cols-3">
            {!isView && (
              <div>
                <label htmlFor="calc-vue" className="etiquette">{t("calcul.nomVue")}</label>
                <input id="calc-vue" className="champ" required value={viewName} onChange={(e) => setViewName(e.target.value)} />
              </div>
            )}
            <div>
              <label htmlFor="calc-nom" className="etiquette">{t("calcul.nomChamp")}</label>
              <input id="calc-nom" className="champ" required maxLength={63} value={nom} onChange={(e) => setNom(e.target.value)} />
            </div>
          </div>
          <div>
            <label htmlFor="calc-expr" className="etiquette">{t("calcul.expression")}</label>
            <textarea id="calc-expr" className="champ font-mono" rows={2} required value={expression}
              placeholder={t("calcul.exemple")} aria-describedby="calc-etat"
              onChange={(e) => setExpression(e.target.value)} />
            <div id="calc-etat" aria-live="polite" className="mt-1 text-xs">
              {check?.valide === false && (
                <p className="text-red-700">
                  {check.erreur}
                  {check.position !== null && ` — ${t("calcul.position", { n: check.position + 1 })}`}
                </p>
              )}
              {check?.valide && (
                <p className="text-emerald-700">
                  {t("calcul.valide", { type: t(`assistant.types.${check.type}`, { defaultValue: check.type }) })}{" "}
                  {check.apercu.map((v) => (v === null ? "∅" : String(v))).join(" · ")}
                </p>
              )}
            </div>
          </div>
          <details className="text-xs text-slate-600">
            <summary className="cursor-pointer">{t("calcul.syntaxe")}</summary>
            <p className="mt-1">{t("calcul.syntaxeDetail")}</p>
            <p className="mt-1"><strong>{t("calcul.fonctions")}</strong> : {functions.join(", ")}</p>
          </details>
          <button type="submit" className="btn-primaire" disabled={check?.valide === false}>
            {isView ? t("calcul.ajouter") : t("calcul.creerVue")}
          </button>
        </form>
      )}
    </section>
  );
}
