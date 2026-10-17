import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, put } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatNombre } from "../../lib/format";
import Alert from "../Alert";

export interface MappedAccount {
  compte: string;
  libelle: string | null;
  soldes: Record<string, string>;
  postes: Record<string, string | null>;
  libelles_postes: Record<string, string | null>;
  racines: Record<string, string | null>;
  origine: "auto" | "manuel";
  poste_manuel: string | null;
  poste_crediteur: string | null;
  commentaire: string | null;
  affecte: boolean;
}

export interface Mapping {
  comptes: MappedAccount[];
  non_affectes: string[];
  postes: { code: string; libelle: string; etat: string; nature: string }[];
}

type Filter = "non_affectes" | "manuels" | "tous";
const PERIODS = ["N", "N-1"] as const;

/** Affectation des comptes aux postes (REV-08), comptes à double sens (REV-09). */
export default function MappingPanel({ file, mapping, onChange }: { file: AuditFile; mapping: Mapping; onChange: (m: Mapping) => void }) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState<Filter>(mapping.non_affectes.length ? "non_affectes" : "tous");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState({ poste: "", poste_crediteur: "", commentaire: "" });
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/mapping`;

  const groups = useMemo(() => {
    const out: Record<string, Mapping["postes"]> = {};
    mapping.postes.forEach((p) => (out[p.etat] ??= []).push(p));
    return out;
  }, [mapping.postes]);
  const options = (
    <>
      <option value="">—</option>
      {Object.entries(groups).map(([etat, list]) => (
        <optgroup key={etat} label={t(`affectation.etats.${etat}`, { defaultValue: etat })}>
          {list.map((p) => <option key={p.code} value={p.code}>{p.code} – {p.libelle}</option>)}
        </optgroup>
      ))}
    </>
  );

  const rows = mapping.comptes.filter((a) => {
    if (filter === "non_affectes" && a.affecte) return false;
    if (filter === "manuels" && a.origine !== "manuel") return false;
    const q = search.trim().toLowerCase();
    return !q || a.compte.startsWith(q) || (a.libelle ?? "").toLowerCase().includes(q);
  });

  const edit = (a: MappedAccount) => {
    setEditing(a.compte);
    setForm({ poste: a.poste_manuel ?? a.postes.N ?? a.postes["N-1"] ?? "", poste_crediteur: a.poste_crediteur ?? "", commentaire: a.commentaire ?? "" });
  };
  const run = async (fn: () => Promise<Mapping>) => {
    setError(null);
    try {
      onChange(await fn());
      setEditing(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const save = (compte: string) =>
    run(() => put<Mapping>(`${url}/${compte}`, { poste: form.poste, poste_crediteur: form.poste_crediteur || null, commentaire: form.commentaire || null }));
  const reset = (compte: string) => run(() => api<Mapping>(`${url}/${compte}`, { method: "DELETE" }));

  return (
    <section className="carte space-y-3" aria-labelledby="affectation-titre">
      <h2 id="affectation-titre" className="text-base font-semibold">{t("affectation.titre")}</h2>
      <p className="text-sm text-slate-600">{t("affectation.aide")}</p>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div className="flex flex-wrap items-end gap-3">
        <fieldset className="flex gap-3 text-sm">
          <legend className="sr-only">{t("affectation.filtre")}</legend>
          {(["non_affectes", "manuels", "tous"] as Filter[]).map((k) => (
            <label key={k} className="flex items-center gap-1">
              <input type="radio" name="aff-filtre" checked={filter === k} onChange={() => setFilter(k)} />
              {t(`affectation.filtres.${k}`)}
            </label>
          ))}
        </fieldset>
        <div>
          <label htmlFor="aff-q" className="etiquette">{t("affectation.recherche")}</label>
          <input id="aff-q" className="champ" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </div>
      {rows.length === 0 ? <p className="text-sm text-slate-600">{t("affectation.aucun")}</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-600">
              <tr>
                <th scope="col" className="py-1 pr-3">{t("affectation.col.compte")}</th>
                {PERIODS.map((p) => <th key={p} scope="col" className="py-1 pr-3 text-right">{t("affectation.col.solde", { periode: p })}</th>)}
                {PERIODS.map((p) => <th key={p} scope="col" className="py-1 pr-3">{t("affectation.col.poste", { periode: p })}</th>)}
                <th scope="col" className="py-1"><span className="sr-only">{t("affectation.col.actions")}</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((a) => (
                <tr key={a.compte} className={a.affecte ? "" : "bg-red-50"}>
                  <td className="py-1 pr-3"><span className="font-mono">{a.compte}</span> {a.libelle}</td>
                  {PERIODS.map((p) => <td key={p} className="py-1 pr-3 text-right font-mono text-xs">{a.soldes[p] !== undefined ? formatNombre(Number(a.soldes[p])) : ""}</td>)}
                  {PERIODS.map((p) => (
                    <td key={p} className="py-1 pr-3 text-xs">
                      {a.soldes[p] === undefined ? "" : a.postes[p] ? (
                        <span title={a.racines[p] ? t("affectation.parRacine", { racine: a.racines[p] }) : t("affectation.manuelle")}>
                          {a.postes[p]} – {a.libelles_postes[p]}
                        </span>
                      ) : <strong className="text-red-700">{t("affectation.nonAffecte")}</strong>}
                    </td>
                  ))}
                  <td className="py-1 text-right text-xs">
                    {a.origine === "manuel" && <span className="mr-2 rounded bg-slate-100 px-1">{t("affectation.manuelle")}</span>}
                    {file.peut_travailler && <button type="button" className="underline" onClick={() => edit(a)} aria-label={t("affectation.modifierCompte", { compte: a.compte })}>{t("affectation.modifier")}</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && (
        <form className="grid gap-2 rounded border border-slate-200 p-3 md:grid-cols-4" onSubmit={(e) => { e.preventDefault(); void save(editing); }}>
          <p className="md:col-span-4 font-medium">{t("affectation.edition", { compte: editing })}</p>
          <div><label htmlFor="aff-poste" className="etiquette">{t("affectation.poste")}</label><select id="aff-poste" className="champ" required value={form.poste} onChange={(e) => setForm({ ...form, poste: e.target.value })}>{options}</select></div>
          <div><label htmlFor="aff-cred" className="etiquette">{t("affectation.posteCrediteur")}</label><select id="aff-cred" className="champ" value={form.poste_crediteur} onChange={(e) => setForm({ ...form, poste_crediteur: e.target.value })}>{options}</select></div>
          <div><label htmlFor="aff-com" className="etiquette">{t("affectation.commentaire")}</label><input id="aff-com" className="champ" value={form.commentaire} onChange={(e) => setForm({ ...form, commentaire: e.target.value })} /></div>
          <div className="flex items-end gap-2">
            <button type="submit" className="btn-primaire">{t("commun.enregistrer")}</button>
            {mapping.comptes.find((a) => a.compte === editing)?.origine === "manuel" && (
              <button type="button" className="btn-secondaire" onClick={() => void reset(editing)}>{t("affectation.automatique")}</button>
            )}
            <button type="button" className="btn-secondaire" onClick={() => setEditing(null)}>{t("commun.annuler")}</button>
          </div>
        </form>
      )}
    </section>
  );
}
