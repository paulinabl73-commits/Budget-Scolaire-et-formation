import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import Alert from "../Alert";

interface Rule { id: string; pays: string; code: string; libelle: string; sens: string; racines: string[]; pourcentage: string; exercice: number | null }

/** Réintégrations et déductions fiscales par pays (RCO-20). */
export default function FiscalRulesPanel() {
  const { t } = useTranslation();
  const [rules, setRules] = useState<Rule[]>([]);
  const [f, setF] = useState({ pays: "", code: "", libelle: "", sens: "reintegration", racines: "", pourcentage: "100" });
  const [error, setError] = useState<string | null>(null);
  const load = () => api<Rule[]>("/fiscal-rules").then(setRules).catch((e: Error) => setError(e.message));
  useEffect(() => {
    void load();
  }, []);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await post("/fiscal-rules", { ...f, racines: f.racines.split(/[;, ]+/).filter(Boolean) });
      setF({ ...f, code: "", libelle: "", racines: "" });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <section className="carte space-y-3" aria-labelledby="fr-titre">
      <h2 id="fr-titre" className="text-base font-semibold">{t("passageFiscal.reglesTitre")}</h2>
      <p className="text-sm text-slate-600">{t("passageFiscal.reglesAide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <ul className="divide-y divide-slate-100 text-sm">
        {rules.map((r) => (
          <li key={r.id} className="flex justify-between gap-2 py-1">
            <span><span className="font-mono">{r.pays} · {r.code}</span> {r.libelle} · {t(`passageFiscal.sensValeurs.${r.sens}`)} · {r.racines.join(", ") || "—"} · {r.pourcentage} %</span>
            <button type="button" className="underline" onClick={() => void del(`/fiscal-rules/${r.id}`).then(load)}>{t("calendrier.supprimer")}</button>
          </li>
        ))}
      </ul>
      <form onSubmit={(e) => void submit(e)} className="grid gap-3 md:grid-cols-6">
        {(["pays", "code", "libelle", "racines", "pourcentage"] as const).map((k) => (
          <div key={k} className={k === "libelle" ? "md:col-span-2" : ""}>
            <label htmlFor={`fr-${k}`} className="etiquette">{t(`passageFiscal.champs.${k}`)}</label>
            <input id={`fr-${k}`} className="champ" required={k !== "racines"} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
          </div>
        ))}
        <div>
          <label htmlFor="fr-sens" className="etiquette">{t("passageFiscal.sens")}</label>
          <select id="fr-sens" className="champ" value={f.sens} onChange={(e) => setF({ ...f, sens: e.target.value })}>
            <option value="reintegration">{t("passageFiscal.sensValeurs.reintegration")}</option>
            <option value="deduction">{t("passageFiscal.sensValeurs.deduction")}</option>
          </select>
        </div>
        <div className="md:col-span-6"><button type="submit" className="btn-secondaire">{t("passageFiscal.ajouterRegle")}</button></div>
      </form>
    </section>
  );
}
