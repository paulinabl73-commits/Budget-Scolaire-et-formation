import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import Alert from "../Alert";

interface Item { code: string; libelle: string; unite: string; controle: string }
interface Param { id: string; pays: string; code: string; libelle: string; valeur: string; unite: string | null; exercice: number | null }

/** Taux et barèmes fiscaux par pays et par exercice (RCO-22). */
export default function FiscalParametersPanel() {
  const { t } = useTranslation();
  const [data, setData] = useState<{ catalogue: Item[]; parametres: Param[] } | null>(null);
  const [f, setF] = useState({ pays: "", code: "", valeur: "", exercice: "" });
  const [error, setError] = useState<string | null>(null);
  const load = () => api<{ catalogue: Item[]; parametres: Param[] }>("/fiscal-parameters").then(setData).catch((e: Error) => setError(e.message));
  useEffect(() => {
    void load();
  }, []);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await post("/fiscal-parameters", { ...f, exercice: f.exercice ? Number(f.exercice) : null });
      setF({ ...f, valeur: "" });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  if (!data) return null;
  return (
    <section className="carte space-y-3" aria-labelledby="fp-titre">
      <h2 id="fp-titre" className="text-base font-semibold">{t("parametresFiscaux.titre")}</h2>
      <p className="text-sm text-slate-600">{t("parametresFiscaux.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <ul className="divide-y divide-slate-100 text-sm">
        {data.parametres.map((p) => (
          <li key={p.id} className="flex justify-between gap-2 py-1">
            <span><span className="font-mono">{p.pays}</span> · {p.libelle} : {p.valeur}{p.unite === "%" ? " %" : ""} · {p.exercice ? t("parametresFiscaux.aPartirDe", { exercice: p.exercice }) : t("parametresFiscaux.tousExercices")}</span>
            <button type="button" className="underline" onClick={() => void del(`/fiscal-parameters/${p.id}`).then(load)}>{t("calendrier.supprimer")}</button>
          </li>
        ))}
      </ul>
      <form onSubmit={(e) => void submit(e)} className="grid gap-3 md:grid-cols-4">
        <div><label htmlFor="fp-pays" className="etiquette">{t("calendrier.champs.pays")}</label><input id="fp-pays" className="champ" required value={f.pays} onChange={(e) => setF({ ...f, pays: e.target.value })} /></div>
        <div>
          <label htmlFor="fp-code" className="etiquette">{t("parametresFiscaux.parametre")}</label>
          <select id="fp-code" className="champ" required value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })}>
            <option value="">—</option>
            {data.catalogue.map((c) => <option key={c.code} value={c.code}>{c.libelle} ({c.unite})</option>)}
          </select>
        </div>
        <div><label htmlFor="fp-valeur" className="etiquette">{t("parametresFiscaux.valeur")}</label><input id="fp-valeur" className="champ" inputMode="decimal" required value={f.valeur} onChange={(e) => setF({ ...f, valeur: e.target.value })} /></div>
        <div><label htmlFor="fp-ex" className="etiquette">{t("parametresFiscaux.exercice")}</label><input id="fp-ex" type="number" className="champ" value={f.exercice} onChange={(e) => setF({ ...f, exercice: e.target.value })} /></div>
        <div className="md:col-span-4"><button type="submit" className="btn-secondaire">{t("parametresFiscaux.ajouter")}</button></div>
      </form>
    </section>
  );
}
