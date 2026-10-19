import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, download } from "../../api/client";
import { formatDate } from "../../lib/format";
import Alert from "../Alert";

export interface PermanentDoc {
  id: string;
  categorie: string;
  libelle: string;
  date_document: string | null;
  date_validite: string | null;
  commentaire: string | null;
  fichiers: { id: string; nom_fichier: string }[];
  expire?: boolean;
}
const CATEGORIES = ["statuts", "rccm", "identifiant_fiscal", "organigramme", "contrat", "bail", "emprunt", "credit_bail", "caution", "autre"];

/** Dossier permanent du client (RCO-05). */
export default function PermanentPanel({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const [docs, setDocs] = useState<PermanentDoc[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const url = `/clients/${clientId}/permanent`;
  const load = useCallback(() => api<PermanentDoc[]>(url).then(setDocs), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    for (const k of ["date_document", "date_validite"]) if (!form.get(k)) form.delete(k);
    if (!(form.get("file") as File | null)?.size) form.delete("file");
    const target = e.currentTarget;
    try {
      setDocs(await api<PermanentDoc[]>(url, { method: "POST", body: form }));
      target.reset();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const remove = async (id: string) => {
    await del(`/permanent/${id}`).catch((e: Error) => setError(e.message));
    await load();
  };
  return (
    <section className="carte space-y-3" aria-labelledby="cl-permanent">
      <h2 id="cl-permanent" className="text-base font-semibold">{t("permanent.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      {docs && docs.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600">
            <tr>{["document", "date", "validite", "fichiers"].map((k) => <th key={k} scope="col" className="py-1 pr-3">{t(`permanent.${k}`)}</th>)}<th /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {docs.map((d) => (
              <tr key={d.id} className={d.expire ? "bg-red-50" : ""}>
                <th scope="row" className="py-1 pr-3 font-normal">{t(`permanent.categories.${d.categorie}`)} · {d.libelle}</th>
                <td className="py-1 pr-3">{d.date_document ? formatDate(d.date_document) : "—"}</td>
                <td className="py-1 pr-3">{d.date_validite ? formatDate(d.date_validite) : "—"}{d.expire && <span className="ml-1 font-medium text-red-700">{t("permanent.expire")}</span>}</td>
                <td className="py-1 pr-3">{d.fichiers.map((f) => <button key={f.id} type="button" className="mr-2 underline" onClick={() => void download(`/client-files/${f.id}/content`, undefined, f.nom_fichier)}>{f.nom_fichier}</button>)}</td>
                <td className="py-1 text-right"><button type="button" className="underline" onClick={() => void remove(d.id)}>{t("permanent.retirer")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form onSubmit={(e) => void submit(e)} className="grid gap-3 md:grid-cols-3" aria-label={t("permanent.ajouter")}>
        <div>
          <label htmlFor="pd-cat" className="etiquette">{t("permanent.categorie")}</label>
          <select id="pd-cat" name="categorie" className="champ">{CATEGORIES.map((c) => <option key={c} value={c}>{t(`permanent.categories.${c}`)}</option>)}</select>
        </div>
        <div className="md:col-span-2">
          <label htmlFor="pd-lib" className="etiquette">{t("permanent.document")}</label>
          <input id="pd-lib" name="libelle" className="champ" required minLength={2} />
        </div>
        <div><label htmlFor="pd-date" className="etiquette">{t("permanent.date")}</label><input id="pd-date" name="date_document" type="date" className="champ" /></div>
        <div><label htmlFor="pd-val" className="etiquette">{t("permanent.validite")}</label><input id="pd-val" name="date_validite" type="date" className="champ" /></div>
        <div><label htmlFor="pd-file" className="etiquette">{t("permanent.fichier")}</label><input id="pd-file" name="file" type="file" className="champ" /></div>
        <div className="md:col-span-3"><button type="submit" className="btn-secondaire">{t("permanent.ajouter")}</button></div>
      </form>
    </section>
  );
}
