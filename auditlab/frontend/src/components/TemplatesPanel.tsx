import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../api/client";
import type { EngagementTemplate, Risk } from "../api/types";
import Alert from "./Alert";

export default function TemplatesPanel({ canManage }: { canManage: boolean }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<EngagementTemplate[]>([]);
  const [risks, setRisks] = useState<Risk[]>([]);
  const [adding, setAdding] = useState(false);
  const [f, setF] = useState({ nom: "", description: "", budget_jours: "", ids: [] as string[] });
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(null);

  const load = useCallback(async () => setRows(await api<EngagementTemplate[]>("/templates")), []);
  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
    api<Risk[]>("/library/risks").then(setRisks).catch(() => setRisks([]));
  }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setMessage(null);
    try {
      await action();
      setMessage({ kind: "succes", text: t("modeles.cree") });
      await load();
      return true;
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
      return false;
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await run(() =>
      post("/templates", {
        nom: f.nom,
        description: f.description || null,
        budget_jours: f.budget_jours ? Number(f.budget_jours) : null,
        library_risk_ids: f.ids,
      }),
    );
    if (ok) {
      setAdding(false);
      setF({ nom: "", description: "", budget_jours: "", ids: [] });
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">{t("modeles.intro")}</p>
        {canManage && !adding && (
          <button type="button" className="btn-primaire" onClick={() => setAdding(true)}>{t("modeles.nouveau")}</button>
        )}
      </div>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {adding && (
        <form onSubmit={submit} className="carte grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="tp-nom" className="etiquette">{t("modeles.nom")}</label>
            <input id="tp-nom" className="champ" required value={f.nom} onChange={(e) => setF({ ...f, nom: e.target.value })} />
          </div>
          <div>
            <label htmlFor="tp-budget" className="etiquette">{t("modeles.budget")}</label>
            <input id="tp-budget" type="number" min={0.5} step={0.5} className="champ" value={f.budget_jours}
              onChange={(e) => setF({ ...f, budget_jours: e.target.value })} />
          </div>
          <div className="col-span-2">
            <label htmlFor="tp-desc" className="etiquette">{t("modeles.description")}</label>
            <input id="tp-desc" className="champ" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </div>
          <fieldset className="col-span-2">
            <legend className="etiquette">{t("modeles.risques")}</legend>
            <div className="mt-1 grid grid-cols-1 gap-1 md:grid-cols-2">
              {risks.map((r) => (
                <label key={r.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={f.ids.includes(r.id)}
                    onChange={(e) => setF({ ...f, ids: e.target.checked ? [...f.ids, r.id] : f.ids.filter((x) => x !== r.id) })} />
                  {t(`bibliotheque.cycles.${r.cycle}`)} — {r.libelle}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="col-span-2 flex gap-2">
            <button type="submit" className="btn-primaire" disabled={!f.ids.length}>{t("modeles.creer")}</button>
            <button type="button" className="btn-secondaire" onClick={() => setAdding(false)}>{t("commun.annuler")}</button>
          </div>
        </form>
      )}
      {rows.length === 0 ? (
        <p className="carte text-sm text-slate-600">{t("modeles.aucun")}</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((m) => (
            <li key={m.id} className="carte flex items-start justify-between gap-4">
              <div>
                <p className="font-medium">{m.nom}</p>
                {m.description && <p className="text-sm text-slate-700">{m.description}</p>}
                <p className="text-xs text-slate-600">
                  {t("modeles.contenu", { risques: m.nb_risques, controles: m.nb_controles, procedures: m.nb_procedures })}
                  {m.budget_jours !== null && ` · ${m.budget_jours} j`}
                </p>
              </div>
              {canManage && (
                <button type="button" className="text-sm text-red-800 underline"
                  onClick={() => window.confirm(t("modeles.confirmerSuppression", { nom: m.nom })) && run(() => del(`/templates/${m.id}`))}>
                  {t("commun.supprimer")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
