import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api, del, post } from "../../api/client";
import type { AuditFile } from "../../api/types";
import { formatDate, formatDecimal } from "../../lib/format";
import Alert from "../Alert";
import GenerateEntry from "./GenerateEntry";

interface Row { id: string; code: string; libelle: string; composant_de: string | null; compte_immobilisation: string; date_mise_en_service: string; mode: string; duree_annees: number; valeur_origine: string; acquisition: boolean; cession: boolean; resultat_cession: string | null; cumul_debut: string; dotation: string; cumul_fin: string; vnc: string }
interface Register { immobilisations: Row[]; totaux: Record<string, string>; rapprochement: { compte: string; tableau: string; balance: string; ecart: string }[] }
const EMPTY = { code: "", libelle: "", compte_immobilisation: "", compte_amortissement: "", compte_dotation: "", date_mise_en_service: "", valeur_origine: "", mode: "lineaire", duree_annees: "", coefficient: "", composant_de: "", date_cession: "", prix_cession: "" };

/** Tableau des immobilisations et dotation de l'exercice (RCO-11). */
export default function FixedAssetsPanel({ file }: { file: AuditFile }) {
  const { t } = useTranslation();
  const [data, setData] = useState<Register | null>(null);
  const [f, setF] = useState<Record<string, string>>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const url = `/audit-files/${file.id}/fixed-assets`;
  const load = useCallback(() => api<Register>(url).then(setData), [url]);
  useEffect(() => {
    load().catch((e: Error) => setError(e.message));
  }, [load]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" ? null : v]));
    body.duree_annees = Number(f.duree_annees) as unknown as string;
    try {
      setData(await post<Register>(url, body));
      setF(EMPTY);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const input = (k: string, type = "text") => (
    <div key={k}>
      <label htmlFor={`fa-${k}`} className="etiquette">{t(`immobilisations.champs.${k}`)}</label>
      <input id={`fa-${k}`} type={type} className="champ" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </div>
  );
  if (!data) return error ? <Alert kind="erreur">{error}</Alert> : null;
  return (
    <section className="carte space-y-3" aria-labelledby="fa-titre">
      <h2 id="fa-titre" className="text-base font-semibold">{t("immobilisations.titre")}</h2>
      {error && <Alert kind="erreur">{error}</Alert>}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-600">
            <tr>{["bien", "service", "mode", "valeur", "debut", "dotation", "fin", "vnc"].map((k) => <th key={k} scope="col" className="py-1 pr-3">{t(`immobilisations.col.${k}`)}</th>)}<th /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.immobilisations.map((r) => (
              <tr key={r.id}>
                <th scope="row" className={`py-1 pr-3 font-normal ${r.composant_de ? "pl-4" : ""}`}>
                  <span className="font-mono text-xs">{r.code}</span> {r.libelle} <span className="text-xs text-slate-600">{r.compte_immobilisation}</span>
                  {r.acquisition && <span className="ml-1 rounded bg-emerald-50 px-1 text-xs text-emerald-800">{t("immobilisations.acquisition")}</span>}
                  {r.cession && <span className="ml-1 rounded bg-amber-50 px-1 text-xs text-amber-800">{t("immobilisations.cede", { resultat: formatDecimal(r.resultat_cession ?? "0") })}</span>}
                </th>
                <td className="py-1 pr-3">{formatDate(r.date_mise_en_service)}</td>
                <td className="py-1 pr-3">{t(`immobilisations.modes.${r.mode}`)} {r.duree_annees} {t("immobilisations.ans")}</td>
                {[r.valeur_origine, r.cumul_debut, r.dotation, r.cumul_fin, r.vnc].map((v, i) => <td key={i} className="py-1 pr-3 text-right font-mono">{formatDecimal(v)}</td>)}
                <td className="py-1"><button type="button" className="underline" onClick={() => void del(`${url}/${r.id}`).then(load)}>{t("immobilisations.retirer")}</button></td>
              </tr>
            ))}
          </tbody>
          <tfoot className="font-medium">
            <tr><th scope="row" colSpan={3} className="py-1 pr-3 text-left">{t("immobilisations.total")}</th><td className="py-1 pr-3 text-right font-mono">{formatDecimal(data.totaux.valeur_origine)}</td><td /><td className="py-1 pr-3 text-right font-mono">{formatDecimal(data.totaux.dotation)}</td><td className="py-1 pr-3 text-right font-mono">{formatDecimal(data.totaux.cumul_fin)}</td><td className="py-1 pr-3 text-right font-mono">{formatDecimal(data.totaux.vnc)}</td><td /></tr>
          </tfoot>
        </table>
      </div>
      {data.rapprochement.length > 0 && (
        <p className="text-sm">{t("immobilisations.rapprochement")} {data.rapprochement.map((r) => `${r.compte} : ${formatDecimal(r.ecart)}`).join(" · ")}</p>
      )}
      {file.peut_travailler && (
        <>
          <GenerateEntry url={`${url}/entry`} disabled={data.immobilisations.length === 0} />
          <form onSubmit={(e) => void submit(e)} className="grid gap-3 md:grid-cols-4" aria-label={t("immobilisations.ajouter")}>
            {input("code")}
            <div className="md:col-span-3">{input("libelle")}</div>
            {input("compte_immobilisation")}
            {input("compte_amortissement")}
            {input("compte_dotation")}
            {input("date_mise_en_service", "date")}
            {input("valeur_origine")}
            <div>
              <label htmlFor="fa-mode" className="etiquette">{t("immobilisations.champs.mode")}</label>
              <select id="fa-mode" className="champ" value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}>
                {["lineaire", "degressif"].map((m) => <option key={m} value={m}>{t(`immobilisations.modes.${m}`)}</option>)}
              </select>
            </div>
            {input("duree_annees", "number")}
            {f.mode === "degressif" && input("coefficient")}
            <div>
              <label htmlFor="fa-parent" className="etiquette">{t("immobilisations.champs.composant_de")}</label>
              <select id="fa-parent" className="champ" value={f.composant_de} onChange={(e) => setF({ ...f, composant_de: e.target.value })}>
                <option value="">—</option>
                {data.immobilisations.filter((r) => !r.composant_de).map((r) => <option key={r.id} value={r.id}>{r.code} · {r.libelle}</option>)}
              </select>
            </div>
            {input("date_cession", "date")}
            {input("prix_cession")}
            <div className="md:col-span-4"><button type="submit" className="btn-secondaire">{t("immobilisations.ajouter")}</button></div>
          </form>
        </>
      )}
    </section>
  );
}
