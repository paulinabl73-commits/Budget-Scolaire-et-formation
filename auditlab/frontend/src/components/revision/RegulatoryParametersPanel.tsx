import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { formatDecimal } from "../../lib/format";
import { can, PERM } from "../../lib/permissions";
import Alert from "../Alert";

interface Framework { id: string; code: string; version: string; libelle: string; branches: { code: string; libelle: string }[] }
interface CatalogItem { code: string; libelle: string; unite: string; par_branche: boolean; par_categorie?: boolean; controle: string }
interface Param { id: string; code: string; libelle: string; valeur: string; unite: string | null; pays: string | null; exercice: number | null; branche: string | null }

/** Paramètres réglementaires par pays, exercice et branche (CIP-09). */
export default function RegulatoryParametersPanel() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const manager = can(user?.permissions, PERM.FRAMEWORKS_MANAGE);
  const [frameworks, setFrameworks] = useState<Framework[]>([]);
  const [fw, setFw] = useState("");
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [params, setParams] = useState<Param[]>([]);
  const [form, setForm] = useState({ code: "taux_cotisation", categorie: "", valeur: "", pays: "", exercice: "", branche: "" });
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Framework[]>("/frameworks").then((list) => {
      setFrameworks(list);
      setFw((list.find((f) => f.code === "CIPRES") ?? list[0])?.id ?? "");
    }).catch((e: Error) => setError(e.message));
  }, []);
  const load = useCallback(async () => {
    if (!fw) return;
    const r = await api<{ catalogue: CatalogItem[]; parametres: Param[] }>(`/frameworks/${fw}/parameters`);
    setCatalog(r.catalogue);
    setParams(r.parametres);
  }, [fw]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const item = catalog.find((c) => c.code === form.code);
  const framework = frameworks.find((f) => f.id === fw);
  const add = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await post(`/frameworks/${fw}/parameters`, {
        code: item?.par_categorie ? `${form.code}:${form.categorie.trim()}` : form.code,
        libelle: item?.par_categorie ? `${item.libelle} – ${form.categorie}` : item?.libelle ?? form.code,
        valeur: form.valeur.replace(/\s/g, "").replace(",", "."), unite: item?.unite ?? null,
        pays: form.pays || null, exercice: form.exercice ? Number(form.exercice) : null, branche: form.branche || null,
      });
      setForm({ ...form, valeur: "" });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <section className="carte space-y-3" aria-labelledby="par-titre">
      <h2 id="par-titre" className="text-lg font-semibold">{t("parametres.titre")}</h2>
      <p className="text-sm text-slate-600">{t("parametres.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div><label htmlFor="par-fw" className="etiquette">{t("parametres.referentiel")}</label>
        <select id="par-fw" className="champ max-w-md" value={fw} onChange={(e) => setFw(e.target.value)}>{frameworks.map((f) => <option key={f.id} value={f.id}>{f.code} {f.version}</option>)}</select></div>
      <table className="w-full text-sm">
        <thead className="text-xs text-slate-600"><tr>{["parametre", "valeur", "pays", "exercice", "branche", ""].map((k) => <th key={k} scope="col" className="py-1 pr-3 text-left">{k && t(`parametres.col.${k}`)}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100">
          {params.map((p) => (
            <tr key={p.id}><td className="py-1 pr-3">{p.libelle}</td><td className="py-1 pr-3 font-mono">{formatDecimal(p.valeur)} {p.unite}</td><td className="py-1 pr-3">{p.pays ?? t("parametres.tous")}</td><td className="py-1 pr-3">{p.exercice ?? t("parametres.tous")}</td><td className="py-1 pr-3">{p.branche ?? "—"}</td>
              <td className="py-1 text-right">{manager && <button type="button" className="text-xs text-red-700 underline" onClick={() => void del(`/regulatory-parameters/${p.id}`).then(load)}>{t("parametres.supprimer")}</button>}</td></tr>
          ))}
        </tbody>
      </table>
      {params.length === 0 && <p className="text-sm text-slate-600">{t("parametres.aucun")}</p>}
      {manager && (
        <form onSubmit={add} className="grid gap-2 md:grid-cols-6">
          <div className="md:col-span-2"><label htmlFor="par-code" className="etiquette">{t("parametres.col.parametre")}</label>
            <select id="par-code" className="champ" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })}>{catalog.map((c) => <option key={c.code} value={c.code}>{c.libelle} ({c.controle})</option>)}</select></div>
          {item?.par_categorie && <div><label htmlFor="par-cat" className="etiquette">{t("parametres.categorie")}</label><input id="par-cat" className="champ" required value={form.categorie} onChange={(e) => setForm({ ...form, categorie: e.target.value })} /></div>}
          <div><label htmlFor="par-val" className="etiquette">{t("parametres.col.valeur")} ({item?.unite})</label><input id="par-val" className="champ" inputMode="decimal" required value={form.valeur} onChange={(e) => setForm({ ...form, valeur: e.target.value })} /></div>
          <div><label htmlFor="par-pays" className="etiquette">{t("parametres.col.pays")}</label><input id="par-pays" className="champ" placeholder={t("parametres.tous")} value={form.pays} onChange={(e) => setForm({ ...form, pays: e.target.value.toUpperCase() })} /></div>
          <div><label htmlFor="par-ex" className="etiquette">{t("parametres.aPartirDe")}</label><input id="par-ex" type="number" className="champ" placeholder={t("parametres.tous")} value={form.exercice} onChange={(e) => setForm({ ...form, exercice: e.target.value })} /></div>
          {item?.par_branche && <div><label htmlFor="par-br" className="etiquette">{t("parametres.col.branche")}</label><select id="par-br" className="champ" value={form.branche} onChange={(e) => setForm({ ...form, branche: e.target.value })}><option value="">{t("parametres.toutes")}</option>{framework?.branches?.map((b) => <option key={b.code} value={b.code}>{b.libelle}</option>)}</select></div>}
          <div className="flex items-end"><button type="submit" className="btn-secondaire">{t("parametres.ajouter")}</button></div>
        </form>
      )}
    </section>
  );
}
