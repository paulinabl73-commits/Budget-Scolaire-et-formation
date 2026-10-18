import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import { REGIMES } from "../../api/portfolio";
import Alert from "../Alert";

interface Rule { id: string; pays: string; code: string; libelle: string; nature: string; periodicite: string; jour: number | null; mois: number | null; decalage_mois: number | null; regimes: string[]; actif: boolean }
const EMPTY = { pays: "", code: "", libelle: "", nature: "fiscal", periodicite: "mensuelle", jour: "", mois: "", decalage_mois: "" };

/** Calendrier fiscal et social paramétrable par pays (RCO-03). */
export default function CalendarRulesPanel() {
  const { t } = useTranslation();
  const [rules, setRules] = useState<Rule[]>([]);
  const [f, setF] = useState<Record<string, string>>(EMPTY);
  const [regimes, setRegimes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = () => api<Rule[]>("/calendar-rules").then(setRules).catch((e: Error) => setError(e.message));
  useEffect(() => {
    void load();
  }, []);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const num = (v: string) => (v === "" ? null : Number(v));
    try {
      await post("/calendar-rules", { ...f, jour: num(f.jour), mois: num(f.mois), decalage_mois: num(f.decalage_mois), regimes });
      setF({ ...EMPTY, pays: f.pays });
      setRegimes([]);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const describe = (r: Rule) => t(`calendrier.regles.${r.periodicite}`, { jour: r.jour ?? "", mois: r.mois ?? "", n: r.decalage_mois ?? "" });
  const input = (k: string, type = "text") => (
    <div key={k}>
      <label htmlFor={`cr-${k}`} className="etiquette">{t(`calendrier.champs.${k}`)}</label>
      <input id={`cr-${k}`} type={type} className="champ" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </div>
  );
  return (
    <section className="carte space-y-3" aria-labelledby="cr-titre">
      <h2 id="cr-titre" className="text-base font-semibold">{t("calendrier.titre")}</h2>
      <p className="text-sm text-slate-600">{t("calendrier.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <ul className="divide-y divide-slate-100 text-sm">
        {rules.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-1">
            <span><span className="font-mono">{r.pays} · {r.code}</span> {r.libelle} — {describe(r)}{r.regimes.length > 0 && ` (${r.regimes.map((x) => t(`portefeuille.regimes.${x}`)).join(", ")})`}</span>
            <button type="button" className="underline" onClick={() => void del(`/calendar-rules/${r.id}`).then(load)}>{t("calendrier.supprimer")}</button>
          </li>
        ))}
      </ul>
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-4">
        {input("pays")}
        {input("code")}
        <div className="md:col-span-2">{input("libelle")}</div>
        <div>
          <label htmlFor="cr-nature" className="etiquette">{t("calendrier.champs.nature")}</label>
          <select id="cr-nature" className="champ" value={f.nature} onChange={(e) => setF({ ...f, nature: e.target.value })}>
            {["fiscal", "social", "juridique"].map((n) => <option key={n} value={n}>{t(`calendrier.natures.${n}`)}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="cr-periodicite" className="etiquette">{t("calendrier.champs.periodicite")}</label>
          <select id="cr-periodicite" className="champ" value={f.periodicite} onChange={(e) => setF({ ...f, periodicite: e.target.value })}>
            {["mensuelle", "trimestrielle", "annuelle", "cloture"].map((n) => <option key={n} value={n}>{t(`calendrier.periodicites.${n}`)}</option>)}
          </select>
        </div>
        {input("jour", "number")}
        {f.periodicite === "annuelle" && input("mois", "number")}
        {f.periodicite === "cloture" && input("decalage_mois", "number")}
        <fieldset className="md:col-span-4">
          <legend className="etiquette">{t("calendrier.champs.regimes")}</legend>
          <div className="flex flex-wrap gap-3 text-sm">
            {REGIMES.map((r) => (
              <label key={r} className="flex items-center gap-1">
                <input type="checkbox" checked={regimes.includes(r)} onChange={(e) => setRegimes(e.target.checked ? [...regimes, r] : regimes.filter((x) => x !== r))} />
                {t(`portefeuille.regimes.${r}`)}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="md:col-span-4"><button type="submit" className="btn-primaire">{t("calendrier.ajouter")}</button></div>
      </form>
    </section>
  );
}
