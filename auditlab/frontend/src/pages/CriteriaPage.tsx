import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, patch, post } from "../api/client";
import type { Axis, CriterionMode, RiskCriterion } from "../api/types";
import Alert from "../components/Alert";

const AXES: Axis[] = ["impact", "probabilite", "autre"];
const MODES: CriterionMode[] = ["note", "anciennete"];
const EMPTY = { code: "", libelle: "", axe: "impact" as Axis, mode: "note" as CriterionMode, poids: 1, ordre: 0 };

export default function CriteriaPage() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<RiskCriterion[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [message, setMessage] = useState<{ kind: "erreur" | "succes"; text: string } | null>(
    null,
  );

  const load = useCallback(async () => setRows(await api<RiskCriterion[]>("/risk/criteria")), []);
  useEffect(() => {
    load().catch((e: Error) => setMessage({ kind: "erreur", text: e.message }));
  }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setMessage(null);
    try {
      await action();
      setMessage({ kind: "succes", text: t("criteres.enregistre") });
      await load();
      return true;
    } catch (e) {
      setMessage({ kind: "erreur", text: (e as Error).message });
      return false;
    }
  };

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (await run(() => post("/risk/criteria", form))) setForm(EMPTY);
  };

  const update = (c: RiskCriterion, changes: Partial<RiskCriterion>) =>
    run(() => patch(`/risk/criteria/${c.id}`, changes));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{t("criteres.titre")}</h1>
        <p className="text-slate-600">{t("criteres.intro")}</p>
      </header>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="carte overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-slate-600">
            <tr>
              {["code", "libelle", "axe", "mode", "poids", "ordre", "actif"].map((k) => (
                <th key={k} scope="col" className="py-2 pr-3">{t(`criteres.${k}`)}</th>
              ))}
              <th scope="col"><span className="sr-only">{t("utilisateurs.actions")}</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {rows.map((c) => (
              <tr key={c.id} className={c.actif ? "" : "text-slate-400"}>
                <td className="py-2 pr-3 font-mono">{c.code}</td>
                <td className="pr-3">{c.libelle}</td>
                <td className="pr-3">{t(`criteres.axes.${c.axe}`)}</td>
                <td className="pr-3">{t(`criteres.modes.${c.mode}`)}</td>
                <td className="pr-3">
                  <input type="number" min={0.1} step={0.5} defaultValue={c.poids}
                    aria-label={`${t("criteres.poids")} — ${c.libelle}`}
                    className="champ mt-0 w-20"
                    onBlur={(e) => {
                      const v = Number(e.target.value);
                      if (v > 0 && v !== c.poids) void update(c, { poids: v });
                    }} />
                </td>
                <td className="pr-3">{c.ordre}</td>
                <td className="pr-3">{c.actif ? t("commun.oui") : t("commun.non")}</td>
                <td>
                  <button type="button" className="text-sm text-marque-700 underline"
                    onClick={() => update(c, { actif: !c.actif })}>
                    {c.actif ? t("criteres.desactiver") : t("criteres.activer")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form onSubmit={onCreate} className="carte grid grid-cols-6 gap-4" aria-label={t("criteres.nouveau")}>
        <h2 className="col-span-6 text-lg font-semibold">{t("criteres.nouveau")}</h2>
        <div>
          <label htmlFor="c-code" className="etiquette">{t("criteres.code")}</label>
          <input id="c-code" className="champ font-mono" required pattern="[A-Z0-9_]+"
            aria-describedby="c-code-aide" value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} />
          <p id="c-code-aide" className="mt-1 text-xs text-slate-600">{t("criteres.codeAide")}</p>
        </div>
        <div className="col-span-2">
          <label htmlFor="c-lib" className="etiquette">{t("criteres.libelle")}</label>
          <input id="c-lib" className="champ" required value={form.libelle}
            onChange={(e) => setForm({ ...form, libelle: e.target.value })} />
        </div>
        <div>
          <label htmlFor="c-axe" className="etiquette">{t("criteres.axe")}</label>
          <select id="c-axe" className="champ" value={form.axe}
            onChange={(e) => setForm({ ...form, axe: e.target.value as Axis })}>
            {AXES.map((a) => <option key={a} value={a}>{t(`criteres.axes.${a}`)}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="c-mode" className="etiquette">{t("criteres.mode")}</label>
          <select id="c-mode" className="champ" value={form.mode}
            onChange={(e) => setForm({ ...form, mode: e.target.value as CriterionMode })}>
            {MODES.map((m) => <option key={m} value={m}>{t(`criteres.modes.${m}`)}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="c-poids" className="etiquette">{t("criteres.poids")}</label>
          <input id="c-poids" type="number" min={0.1} step={0.5} className="champ" required
            value={form.poids} onChange={(e) => setForm({ ...form, poids: Number(e.target.value) })} />
        </div>
        <div className="col-span-6">
          <button type="submit" className="btn-primaire">{t("criteres.ajouter")}</button>
        </div>
      </form>
    </div>
  );
}
